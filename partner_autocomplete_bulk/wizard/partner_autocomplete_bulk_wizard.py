import json
import base64
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PartnerAutocompleteBulkWizard(models.TransientModel):
    _name = 'partner.autocomplete.bulk.wizard'
    _description = 'Partner Autocomplete Bulk Wizard'

    line_ids = fields.One2many(
        'partner.autocomplete.bulk.line', 'wizard_id', string='Autocomplete Lines',
    )

    def action_autocomplete(self):
        """Process selected lines: enrich and update partner records."""
        self.ensure_one()
        selected_lines = self.line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_("Please select at least one partner to autocomplete."))

        errors = []
        for line in selected_lines:
            try:
                autocomplete_payload = json.loads(line.autocomplete_data)
                partner = line.partner_id
                enriched_data = self._get_enriched_data(partner, autocomplete_payload)
                update_values = self._prepare_partner_update_values(
                    partner, autocomplete_payload, enriched_data,
                )
                if update_values:
                    partner.write(update_values)

            except Exception as e:
                error_message = f"Partner '{line.partner_id.name}': {e}"
                errors.append(error_message)
                _logger.error(
                    "Failed to process partner %s (ID: %s): %s",
                    line.partner_id.name, line.partner_id.id, e,
                )

        if errors:
            raise UserError(
                _("Errors occurred during the process:\n\n") + "\n".join(errors)
            )

        return {'type': 'ir.actions.act_window_close'}

    def _get_enriched_data(self, partner, autocomplete_payload):
        """Attempt to enrich partner data via available enrichment methods."""
        if autocomplete_payload.get("skip_enrich"):
            return {}

        enrichment_methods = [
            ("duns", "enrich_by_duns"),
            ("gst", "enrich_by_gst"),
            ("website", "enrich_by_domain"),
        ]

        for key, func_name in enrichment_methods:
            if query := autocomplete_payload.get(key):
                enrich_function = getattr(partner, func_name, None)
                if not enrich_function:
                    _logger.warning(
                        "Enrichment function %s not found on res.partner.", func_name,
                    )
                    continue

                enriched_data = enrich_function(query, timeout=10)
                if enriched_data.get('error'):
                    error_message = enriched_data.get('error_message', 'Unknown error')
                    raise UserError(_(
                        "API Error for %(key)s %(query)s: %(error)s",
                        key=key.upper(), query=query, error=error_message,
                    ))

                return enriched_data
        return {}

    def _prepare_partner_update_values(self, partner, original_payload, enriched_data):
        """Build a dict of field values to write on the partner record."""
        initial_values = dict(enriched_data or {})
        update_values = {}

        if original_payload.get('vat'):
            initial_values['vat'] = original_payload['vat']

        if logo_url := original_payload.get('logo'):
            if logo_base64 := self._fetch_company_logo(logo_url):
                initial_values['image_1920'] = logo_base64

        for field_name in ['phone', 'mobile']:
            if number := initial_values.get(field_name):
                initial_values[field_name] = (
                    self._format_phone_number(partner, number) or number
                )

        for field_name in ['country_id', 'state_id']:
            if value := initial_values.get(field_name):
                if isinstance(value, dict):
                    initial_values[field_name] = value.get('id')

        # Handle known typo in autocomplete API response ('coutry_id' instead of 'country_id')
        if country_data := initial_values.pop('coutry_id', None):
            if not initial_values.get('country_id') and isinstance(country_data, dict):
                initial_values['country_id'] = country_data.get('id')

        for field_name, new_value in initial_values.items():
            if field_name not in partner._fields or field_name == "name" or not new_value:
                continue

            current_value = getattr(partner, field_name, None)
            if isinstance(new_value, str) and isinstance(current_value, str):
                if new_value.lower() == current_value.lower():
                    continue
            update_values[field_name] = new_value

        return update_values

    def _fetch_company_logo(self, logo_url):
        """Download a company logo and return its base64 representation."""
        if not logo_url:
            return False
        try:
            response = requests.get(logo_url, timeout=10, stream=True)
            response.raise_for_status()
            return base64.b64encode(response.content).decode('utf-8')
        except requests.exceptions.RequestException as e:
            _logger.warning(
                "Failed to fetch company logo from %s. Reason: %s", logo_url, e,
            )
            return False

    def _format_phone_number(self, partner, number):
        """Format a phone number to international format using the partner's method."""
        try:
            return partner._phone_format(
                number=number, force_format='INTERNATIONAL',
            )
        except Exception:
            return number


class PartnerAutocompleteBulkLine(models.TransientModel):
    _name = 'partner.autocomplete.bulk.line'
    _description = 'Partner Autocomplete Bulk Line'

    wizard_id = fields.Many2one(
        'partner.autocomplete.bulk.wizard', string='Wizard', ondelete='cascade',
    )
    partner_id = fields.Many2one(
        'res.partner', string='Partner', required=True, ondelete='cascade',
    )
    partner_name = fields.Char(
        related='partner_id.name', string='Partner Name', readonly=True,
    )
    selected = fields.Boolean(string='Autocomplete', default=True)
    autocomplete_data = fields.Text(string='Autocomplete Data')
    autocomplete_data_display = fields.Text(
        string='Autocomplete Data (Preview)',
        compute='_compute_autocomplete_data_display',
        help="Formatted JSON data for preview purposes.",
    )

    @api.depends('autocomplete_data')
    def _compute_autocomplete_data_display(self):
        for line in self:
            if not line.autocomplete_data:
                line.autocomplete_data_display = ''
                continue
            try:
                parsed_json = json.loads(line.autocomplete_data)
                line.autocomplete_data_display = json.dumps(
                    parsed_json, indent=2, ensure_ascii=False,
                )
            except json.JSONDecodeError:
                line.autocomplete_data_display = line.autocomplete_data
