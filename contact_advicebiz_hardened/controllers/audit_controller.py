from odoo import fields, http
from odoo.http import request


class ContactAccessAuditController(http.Controller):
    @http.route(
        "/advicebiz/access_data/audit_list", type="json", auth="user", methods=["POST"]
    )
    def list_audit(self, partner_id=None, offset=0, limit=50, **kwargs):
        """List only audited events for one readable contact; no password values."""
        try:
            partner_id = int(partner_id)
            offset = max(0, int(offset))
            limit = max(1, min(100, int(limit)))
        except (ValueError, TypeError):
            return {"entries": [], "has_more": False}

        partner = request.env["res.partner"].browse(partner_id).exists()
        if not partner:
            return {"entries": [], "has_more": False}
        partner.check_access("read")
        # Never grant broad direct ORM access to sensitive audit metadata.
        # Only trusted endpoint after contact ACL verification can read it.
        if not request.env.user.has_group("base.group_user"):
            return {"entries": [], "has_more": False}
        # Older versions also recorded the Odoo password confirmation as an
        # "unlock" event. It adds no value beside the actual reveal audit.
        # Suppress legacy unlocks from this view without deleting audit rows.
        # Filter at ORM level so offset/limit pagination remains correct.
        events = request.env["tko.contact.access.audit"].sudo().search(
            [("partner_id", "=", partner.id), ("action", "!=", "unlock")],
            offset=offset,
            limit=limit + 1,
        )
        local_user = request.env.user
        result = []
        for event in events[:limit]:
            when = fields.Datetime.context_timestamp(
                event.with_context(tz=local_user.tz), event.occurred_at
            )
            result.append({
                "id": event.id,
                "title": event.title,
                "details": event.details or "",
                "action": event.action,
                "platform": event.platform or "",
                "user": event.actor_id.name or "—",
                "when": when.strftime("%d/%m/%Y %H:%M:%S"),
            })
        return {"entries": result, "has_more": len(events) > limit}
