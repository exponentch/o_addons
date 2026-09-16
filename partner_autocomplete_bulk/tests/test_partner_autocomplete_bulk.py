import json
from unittest.mock import patch, MagicMock

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestFindExactMatch(TransactionCase):
    """Tests for the _find_exact_match method on res.partner."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Company',
            'is_company': True,
        })

    def test_match_found(self):
        results = [
            {'name': 'Test Company', 'vat': 'BE0123456789'},
            {'name': 'Other Corp', 'vat': 'XX'},
        ]
        match = self.partner._find_exact_match(results, 'Test Company')
        self.assertEqual(match['vat'], 'BE0123456789')

    def test_case_insensitive(self):
        results = [{'name': 'TEST COMPANY', 'vat': 'BE0123456789'}]
        match = self.partner._find_exact_match(results, 'test company')
        self.assertIsNotNone(match)

    def test_no_match(self):
        results = [{'name': 'Different Company'}]
        match = self.partner._find_exact_match(results, 'Test Company')
        self.assertIsNone(match)

    def test_empty_results(self):
        match = self.partner._find_exact_match([], 'Test Company')
        self.assertIsNone(match)

    def test_none_partner_name(self):
        match = self.partner._find_exact_match(
            [{'name': 'Something'}], None,
        )
        self.assertIsNone(match)

    def test_first_exact_match_returned(self):
        results = [
            {'name': 'Test Company', 'source': 'first'},
            {'name': 'Test Company', 'source': 'second'},
        ]
        match = self.partner._find_exact_match(results, 'Test Company')
        self.assertEqual(match['source'], 'first')


class TestActionBulkAutocomplete(TransactionCase):
    """Tests for the action_bulk_autocomplete method on res.partner."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_1 = cls.env['res.partner'].create({
            'name': 'Acme Corporation',
            'is_company': True,
        })
        cls.partner_2 = cls.env['res.partner'].create({
            'name': 'Beta Industries',
            'is_company': True,
        })

    def test_empty_recordset_raises(self):
        with self.assertRaises(UserError):
            self.env['res.partner'].browse([]).action_bulk_autocomplete()

    def test_too_many_partners_raises(self):
        partners = self.env['res.partner']
        for i in range(81):
            partners |= self.env['res.partner'].create({
                'name': f'Bulk Partner {i}',
            })
        with self.assertRaises(UserError):
            partners.action_bulk_autocomplete()

    def test_no_matches_raises(self):
        with patch.object(
            type(self.env['res.partner']),
            'autocomplete_by_name',
            return_value=[],
        ):
            with self.assertRaises(UserError):
                self.partner_1.action_bulk_autocomplete()

    def test_partner_without_name_skipped(self):
        no_name = self.env['res.partner'].create({
            'name': False,
            'is_company': True,
        })
        with patch.object(
            type(self.env['res.partner']),
            'autocomplete_by_name',
            return_value=[],
        ):
            with self.assertRaises(UserError):
                (no_name | self.partner_1).action_bulk_autocomplete()

    def test_returns_wizard_action(self):
        mock_results = [
            {'name': 'Acme Corporation', 'vat': 'CH123', 'skip_enrich': True},
        ]
        with patch.object(
            type(self.env['res.partner']),
            'autocomplete_by_name',
            return_value=mock_results,
        ):
            action = self.partner_1.action_bulk_autocomplete()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'partner.autocomplete.bulk.wizard')
        wizard = self.env['partner.autocomplete.bulk.wizard'].browse(
            action['res_id'],
        )
        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(wizard.line_ids.partner_id, self.partner_1)

    def test_autocomplete_api_error_skipped(self):
        """If autocomplete_by_name raises, the partner is skipped."""
        mock_results = [
            {'name': 'Beta Industries', 'vat': 'CH456', 'skip_enrich': True},
        ]

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("API unavailable")
            return mock_results

        with patch.object(
            type(self.env['res.partner']),
            'autocomplete_by_name',
            side_effect=side_effect,
        ):
            action = (self.partner_1 | self.partner_2).action_bulk_autocomplete()
        self.assertEqual(action['type'], 'ir.actions.act_window')


class TestWizard(TransactionCase):
    """Tests for the autocomplete wizard."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Partner SA',
            'is_company': True,
        })

    def test_no_selected_lines_raises(self):
        wizard = self.env['partner.autocomplete.bulk.wizard'].create({
            'line_ids': [(0, 0, {
                'partner_id': self.partner.id,
                'selected': False,
                'autocomplete_data': '{}',
            })],
        })
        with self.assertRaises(UserError):
            wizard.action_autocomplete()

    def test_autocomplete_applies_vat(self):
        data = json.dumps({
            'name': 'Test Partner SA',
            'vat': 'CHE-123.456.789',
            'skip_enrich': True,
        })
        wizard = self.env['partner.autocomplete.bulk.wizard'].create({
            'line_ids': [(0, 0, {
                'partner_id': self.partner.id,
                'selected': True,
                'autocomplete_data': data,
            })],
        })
        result = wizard.action_autocomplete()
        self.assertEqual(result['type'], 'ir.actions.act_window_close')
        self.assertEqual(self.partner.vat, 'CHE-123.456.789')

    def test_autocomplete_does_not_overwrite_name(self):
        original_name = self.partner.name
        data = json.dumps({
            'name': 'Completely Different',
            'vat': 'CHE-111.222.333',
            'skip_enrich': True,
        })
        wizard = self.env['partner.autocomplete.bulk.wizard'].create({
            'line_ids': [(0, 0, {
                'partner_id': self.partner.id,
                'selected': True,
                'autocomplete_data': data,
            })],
        })
        wizard.action_autocomplete()
        self.assertEqual(self.partner.name, original_name)

    def test_autocomplete_collects_errors(self):
        """Invalid JSON in autocomplete_data should produce a collected error."""
        wizard = self.env['partner.autocomplete.bulk.wizard'].create({
            'line_ids': [(0, 0, {
                'partner_id': self.partner.id,
                'selected': True,
                'autocomplete_data': 'NOT VALID JSON',
            })],
        })
        with self.assertRaises(UserError):
            wizard.action_autocomplete()


class TestAutocompleteDataDisplay(TransactionCase):
    """Tests for the computed autocomplete_data_display field."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Display Test',
            'is_company': True,
        })

    def test_valid_json(self):
        line = self.env['partner.autocomplete.bulk.line'].create({
            'partner_id': self.partner.id,
            'autocomplete_data': '{"name":"Test","vat":"BE123"}',
        })
        self.assertIn('Test', line.autocomplete_data_display)
        self.assertIn('BE123', line.autocomplete_data_display)

    def test_empty_data(self):
        line = self.env['partner.autocomplete.bulk.line'].create({
            'partner_id': self.partner.id,
            'autocomplete_data': '',
        })
        self.assertEqual(line.autocomplete_data_display, '')

    def test_invalid_json_fallback(self):
        line = self.env['partner.autocomplete.bulk.line'].create({
            'partner_id': self.partner.id,
            'autocomplete_data': 'not json at all',
        })
        self.assertEqual(
            line.autocomplete_data_display, 'not json at all',
        )

    def test_false_data(self):
        line = self.env['partner.autocomplete.bulk.line'].create({
            'partner_id': self.partner.id,
            'autocomplete_data': False,
        })
        self.assertEqual(line.autocomplete_data_display, '')


class TestPreparePartnerUpdateValues(TransactionCase):
    """Tests for _prepare_partner_update_values."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Update Test SA',
            'is_company': True,
        })
        cls.wizard = cls.env['partner.autocomplete.bulk.wizard'].create({})

    def test_skips_name_field(self):
        values = self.wizard._prepare_partner_update_values(
            self.partner, {}, {'name': 'New Name', 'city': 'Geneva'},
        )
        self.assertNotIn('name', values)
        self.assertIn('city', values)

    def test_skips_identical_string_case_insensitive(self):
        self.partner.city = 'Zurich'
        values = self.wizard._prepare_partner_update_values(
            self.partner, {}, {'city': 'zurich'},
        )
        self.assertNotIn('city', values)

    def test_includes_vat_from_payload(self):
        values = self.wizard._prepare_partner_update_values(
            self.partner, {'vat': 'CHE-999.888.777'}, {},
        )
        self.assertEqual(values.get('vat'), 'CHE-999.888.777')

    def test_handles_country_dict(self):
        country = self.env.ref('base.ch')
        values = self.wizard._prepare_partner_update_values(
            self.partner, {},
            {'country_id': {'id': country.id}},
        )
        self.assertEqual(values.get('country_id'), country.id)

    def test_handles_coutry_id_typo(self):
        """API sometimes returns 'coutry_id' instead of 'country_id'."""
        country = self.env.ref('base.ch')
        values = self.wizard._prepare_partner_update_values(
            self.partner, {},
            {'coutry_id': {'id': country.id}},
        )
        self.assertEqual(values.get('country_id'), country.id)

    def test_skips_unknown_fields(self):
        values = self.wizard._prepare_partner_update_values(
            self.partner, {},
            {'nonexistent_field_xyz_123': 'value'},
        )
        self.assertNotIn('nonexistent_field_xyz_123', values)

    def test_skips_empty_values(self):
        values = self.wizard._prepare_partner_update_values(
            self.partner, {}, {'city': '', 'street': False},
        )
        self.assertNotIn('city', values)
        self.assertNotIn('street', values)


class TestFetchCompanyLogo(TransactionCase):
    """Tests for _fetch_company_logo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wizard = cls.env['partner.autocomplete.bulk.wizard'].create({})

    def test_empty_url(self):
        self.assertFalse(self.wizard._fetch_company_logo(''))

    def test_false_url(self):
        self.assertFalse(self.wizard._fetch_company_logo(False))

    @patch(
        'odoo.addons.partner_autocomplete_bulk'
        '.wizard.partner_autocomplete_bulk_wizard.requests.get',
    )
    def test_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.content = b'\x89PNG\r\n'
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        result = self.wizard._fetch_company_logo(
            'https://example.com/logo.png',
        )
        self.assertTrue(result)
        mock_get.assert_called_once()

    @patch(
        'odoo.addons.partner_autocomplete_bulk'
        '.wizard.partner_autocomplete_bulk_wizard.requests.get',
    )
    def test_network_error(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.exceptions.RequestException('err')
        result = self.wizard._fetch_company_logo(
            'https://example.com/logo.png',
        )
        self.assertFalse(result)


class TestGetEnrichedData(TransactionCase):
    """Tests for _get_enriched_data."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Enrich Test',
            'is_company': True,
        })
        cls.wizard = cls.env['partner.autocomplete.bulk.wizard'].create({})

    def test_skip_enrich(self):
        result = self.wizard._get_enriched_data(
            self.partner, {'skip_enrich': True},
        )
        self.assertEqual(result, {})

    def test_no_enrichment_keys(self):
        result = self.wizard._get_enriched_data(
            self.partner, {'name': 'Test'},
        )
        self.assertEqual(result, {})
