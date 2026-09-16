import json
import logging

from odoo import _, models, Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def action_bulk_autocomplete(self):
        """Launch bulk autocomplete wizard for selected partners."""
        if not self:
            raise UserError(_("Please select at least one partner."))

        if len(self) > 80:
            raise UserError(
                _("The maximum limit is 80 partners. Please select fewer partners.")
            )

        wizard_lines = []
        for partner in self:
            if not partner.name:
                continue

            try:
                autocomplete_results = self.env['res.partner'].autocomplete_by_name(
                    query=partner.name,
                    query_country_id=self.env.company.country_id.id,
                    timeout=10,
                )
            except Exception:
                _logger.warning(
                    "Autocomplete query failed for partner '%s' (ID: %s).",
                    partner.name, partner.id,
                )
                continue

            exact_match = self._find_exact_match(autocomplete_results, partner.name)
            if exact_match:
                wizard_lines.append(Command.create({
                    'partner_id': partner.id,
                    'autocomplete_data': json.dumps(exact_match),
                }))

        if not wizard_lines:
            raise UserError(_("No exact matches found for the selected partners."))

        wizard = self.env['partner.autocomplete.bulk.wizard'].create({
            'line_ids': wizard_lines,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _("Bulk Partner Autocomplete"),
            'res_model': 'partner.autocomplete.bulk.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _find_exact_match(self, results, partner_name):
        """Find exact name match in autocomplete results (case-insensitive)."""
        partner_name_lower = partner_name.lower() if partner_name else ''
        for result in results:
            result_name = result.get('name', '')
            if result_name.lower() == partner_name_lower:
                return result
        return None
