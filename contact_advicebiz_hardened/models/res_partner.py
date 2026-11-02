from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    advicebiz_access_data_ids = fields.One2many(
        comodel_name="tko.contact.access.data",
        inverse_name="partner_id",
        string="Dados de acesso",
        copy=False,
    )
