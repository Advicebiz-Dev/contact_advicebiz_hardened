import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .crypto_utils import decrypt_secret, encrypt_secret


_logger = logging.getLogger(__name__)


def _plain_text(value):
    """Return one deterministic plain-text value from a Studio value.

    Studio translatable Char/Text/HTML values are stored as JSONB in Odoo 19.
    Direct SQL may therefore return a ``dict`` (normal psycopg behaviour) or a
    JSON string.  The hardened legacy metadata is intentionally non-translatable,
    so translations are discarded during migration: prefer ``pt_PT``, then
    ``en_US``, then the first non-empty value available.
    """
    if value in (None, False):
        return False

    parsed = value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return False
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                candidate = json.loads(stripped)
                if isinstance(candidate, dict):
                    parsed = candidate
            except (TypeError, ValueError, json.JSONDecodeError):
                # If it is not valid JSON, preserve it as ordinary text.
                parsed = stripped
        else:
            parsed = stripped

    if isinstance(parsed, dict):
        ordered_values = [parsed.get("pt_PT"), parsed.get("en_US")]
        ordered_values.extend(parsed.values())
        for translated in ordered_values:
            if translated in (None, False, ""):
                continue
            text = str(translated).strip()
            if text:
                return text
        return False

    if isinstance(parsed, (list, tuple)):
        parts = [
            str(item).strip()
            for item in parsed
            if item not in (None, False, "") and str(item).strip()
        ]
        return " ".join(parts) or False

    text = str(parsed).strip()
    return text or False


class TkoContactAccessData(models.Model):
    _name = "tko.contact.access.data"
    _description = "Dados de acesso do contacto"
    _order = "site, id"

    partner_id = fields.Many2one(
        "res.partner",
        string="Contacto",
        required=True,
        ondelete="cascade",
        index=True,
    )
    # Keep the legacy Char for idempotent Studio imports and API compatibility.
    # The interface edits platform_id, whose name is synchronised to site.
    site = fields.Char(string="Plataforma (legado)", required=False)
    platform_id = fields.Many2one(
        "tko.contact.access.platform", string="Plataforma", ondelete="restrict", index=True,
    )
    observations = fields.Text(string="Observações")
    url = fields.Char(string="URL")
    username = fields.Char(string="Login")

    # The clear-text value is deliberately non-stored. Existing records use
    # password_encrypted and the browser never receives the clear-text value
    # during a normal read/web_read.
    password = fields.Char(
        string="Password",
        compute="_compute_password",
        inverse="_inverse_password",
        store=False,
        copy=False,
        exportable=False,
    )
    password_encrypted = fields.Text(
        string="Password cifrada",
        copy=False,
        exportable=False,
    )
    password_is_set = fields.Boolean(
        string="Password definida",
        compute="_compute_password_is_set",
        compute_sudo=True,
    )
    password_set_uid = fields.Many2one(
        "res.users",
        string="Palavra-passe gravada por",
        readonly=True,
        copy=False,
    )
    password_set_at = fields.Datetime(
        string="Palavra-passe gravada em",
        readonly=True,
        copy=False,
    )

    # Traceability of credentials migrated from the legacy Studio One2many
    # ``res.partner.x_studio_dados_de_acesso``. These fields are deliberately
    # not shown in the UI; they let the migration be safely re-run without
    # creating duplicates and preserve the ancillary Studio information.
    legacy_studio_id = fields.Integer(
        string="ID Studio legado",
        readonly=True,
        copy=False,
        index=True,
    )
    legacy_studio_description = fields.Char(
        string="Descrição Studio legada",
        readonly=True,
        copy=False,
    )
    legacy_studio_notes = fields.Html(
        string="Notas Studio legadas",
        readonly=True,
        copy=False,
    )
    legacy_studio_sequence = fields.Integer(
        string="Sequência Studio legada",
        readonly=True,
        copy=False,
    )

    # UI helpers. They do not replace the server-side checks below; their only
    # purpose is to make the editable list reflect the permission matrix before
    # the user attempts an operation. New rows use CREATE permission, while
    # existing rows use EDIT permission.
    can_view_password = fields.Boolean(
        string="Pode visualizar a Password",
        compute="_compute_ui_permissions",
        compute_sudo=False,
    )
    can_modify_fields = fields.Boolean(
        string="Pode alterar os campos",
        compute="_compute_ui_permissions",
        compute_sudo=False,
    )
    can_edit_record = fields.Boolean(
        string="Pode editar o registo",
        compute="_compute_ui_permissions",
        compute_sudo=False,
    )
    can_delete_record = fields.Boolean(
        string="Pode apagar o registo",
        compute="_compute_ui_permissions",
        compute_sudo=False,
    )

    @api.depends_context("uid", "company")
    def _compute_ui_permissions(self):
        """Expose the permission matrix to the editable access-data list.

        The contact and the Dados de Acesso tab are always accessible according
        to the normal contact ACLs. Inside the access-data list:
        - VIEW controls only reveal/copy of the stored password;
        - CREATE controls creation of a complete new row;
        - WRITE controls editing of any field on an existing row;
        - DELETE controls deletion of the complete row.
        """
        can_view_password = self._can_view()
        can_create_password = self._can_create()
        can_edit_password = self._can_edit()
        can_delete_password = self._can_delete()
        for record in self:
            is_existing = bool(record._origin.id)
            record.can_view_password = can_view_password
            record.can_edit_record = can_edit_password if is_existing else False
            record.can_delete_record = can_delete_password if is_existing else False
            # New rows require CREATE; every field of an existing row requires
            # WRITE. VIEW remains independent and controls only reveal/copy.
            record.can_modify_fields = (
                can_edit_password if is_existing else can_create_password
            )

    @api.depends("password_encrypted")
    def _compute_password_is_set(self):
        for record in self:
            record.password_is_set = bool(record.password_encrypted)

    def _compute_password(self):
        # Same principle used by Odoo for res.users.password: never disclose a
        # stored secret through an ordinary ORM read.
        for record in self:
            record.password = False

    def _inverse_password(self):
        # Normal create/write calls are translated to password_encrypted by the
        # overrides below. This inverse keeps the computed field writable for
        # the web client and is also safe for less common ORM flows.
        for record in self:
            if record.password:
                record.with_context(_advicebiz_password_inverse=True).write({
                    "password_encrypted": encrypt_secret(record.password),
                    "password_set_uid": self.env.user.id,
                    "password_set_at": fields.Datetime.now(),
                })

    def _auto_init(self):
        """Prepare encrypted storage and migrate legacy credentials safely.

        Two independent legacy sources are handled:

        * the former clear-text ``password`` column of this model;
        * the Studio One2many ``res.partner.x_studio_dados_de_acesso`` whose
          related model is ``x_res_partner_line_261c0``.

        The Studio source is never modified or deleted. Its password is copied
        only after being encrypted with the Fernet key configured for this Odoo
        service. ``legacy_studio_id`` makes the import idempotent across module
        upgrades/restarts.
        """
        result = super()._auto_init()
        cr = self.env.cr

        # A partial unique index makes the Studio import safe even if more than
        # one Odoo worker initializes the registry at the same time. Multiple
        # NULL values remain allowed for credentials created natively here.
        cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                tko_contact_access_data_legacy_studio_id_uniq
            ON tko_contact_access_data (legacy_studio_id)
            WHERE legacy_studio_id IS NOT NULL
            """
        )

        # ------------------------------------------------------------------
        # 1) Migrate the old clear-text password column of our own table.
        # ------------------------------------------------------------------
        cr.execute(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = current_schema()
               AND table_name = 'tko_contact_access_data'
               AND column_name = 'password'
            """
        )
        legacy_column_exists = bool(cr.fetchone())
        if legacy_column_exists:
            cr.execute(
                """
                SELECT id, password
                  FROM tko_contact_access_data
                 WHERE password IS NOT NULL
                   AND password <> ''
                   AND COALESCE(password_encrypted, '') = ''
                """
            )
            legacy_rows = cr.fetchall()

            if legacy_rows:
                encrypted_rows = [
                    (encrypt_secret(clear_password), record_id)
                    for record_id, clear_password in legacy_rows
                ]
                cr.executemany(
                    """
                    UPDATE tko_contact_access_data
                       SET password_encrypted = %s,
                           password_set_uid = COALESCE(password_set_uid, create_uid),
                           password_set_at = COALESCE(password_set_at, create_date, NOW())
                     WHERE id = %s
                    """,
                    encrypted_rows,
                )

            # Keep the physical legacy column for a conservative schema
            # upgrade, but remove every clear-text value from it.
            cr.execute(
                """
                UPDATE tko_contact_access_data
                   SET password = NULL
                 WHERE password IS NOT NULL
                """
            )

        # ------------------------------------------------------------------
        # 2) Import credentials stored historically by Odoo Studio.
        # ------------------------------------------------------------------
        self._migrate_studio_access_data()
        self._sync_existing_platforms()
        self._sync_legacy_observations()
        return result

    @api.model
    def _studio_scalar_text(self, value):
        """Normalise a Studio scalar while discarding translation variants."""
        return _plain_text(value)

    def _migrate_studio_access_data(self):
        """Import the legacy Studio One2many without touching its source data.

        Known Studio structure (confirmed in PRE):
        - source model/table: ``x_res_partner_line_261c0``
        - contact: ``x_res_partner_id`` -> ``res.partner``
        - platform: ``x_studio_plataforma`` -> ``x_plataformas``
        - login: ``x_studio_login``
        - password: ``x_studio_password``
        - optional metadata: ``x_name``, ``x_studio_notas``,
          ``x_studio_sequence``

        Rows missing Platform, Login or Password are deliberately left only in
        Studio because the hardened model requires all three values. This avoids
        inventing credential data merely to satisfy a constraint.
        """
        cr = self.env.cr
        source_table = "x_res_partner_line_261c0"

        cr.execute("SELECT to_regclass(%s)", (source_table,))
        if not cr.fetchone()[0]:
            return

        cr.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = current_schema()
               AND table_name = %s
            """,
            (source_table,),
        )
        source_columns = {row[0] for row in cr.fetchall()}
        required_columns = {
            "id",
            "x_res_partner_id",
            "x_studio_plataforma",
            "x_studio_login",
            "x_studio_password",
        }
        if not required_columns.issubset(source_columns):
            _logger.warning(
                "Studio access-data migration skipped: expected columns are "
                "missing from %s. Missing=%s",
                source_table,
                sorted(required_columns - source_columns),
            )
            return

        # Resolve the display value of the Studio many2one Plataforma. Studio
        # custom models normally use x_name, but use a conservative fallback if
        # the model was customized further.
        platform_names = {}
        cr.execute("SELECT to_regclass(%s)", ("x_plataformas",))
        platform_table_exists = bool(cr.fetchone()[0])
        if platform_table_exists:
            cr.execute(
                """
                SELECT column_name
                  FROM information_schema.columns
                 WHERE table_schema = current_schema()
                   AND table_name = 'x_plataformas'
                """
            )
            platform_columns = {row[0] for row in cr.fetchall()}
            platform_label_column = next(
                (name for name in ("x_name", "name") if name in platform_columns),
                None,
            )
            if platform_label_column:
                # platform_label_column is selected only from the fixed whitelist
                # above, therefore it is safe to interpolate as an identifier.
                cr.execute(
                    f'SELECT id, "{platform_label_column}" FROM x_plataformas'
                )
                platform_names = {
                    row_id: (self._studio_scalar_text(label) or "").strip()
                    for row_id, label in cr.fetchall()
                }

        def source_expr(column_name):
            # column_name comes only from fixed literals below; never from user
            # input. Prefix existing columns with the source alias and emit SQL
            # NULL for optional fields absent in a particular Studio database.
            return f"s.{column_name}" if column_name in source_columns else "NULL"

        cr.execute(
            f"""
            SELECT s.id,
                   s.x_res_partner_id,
                   s.x_studio_plataforma,
                   s.x_studio_login,
                   s.x_studio_password,
                   {source_expr('x_name')} AS legacy_description,
                   {source_expr('x_studio_notas')} AS legacy_notes,
                   {source_expr('x_studio_sequence')} AS legacy_sequence,
                   {source_expr('create_uid')} AS legacy_create_uid,
                   {source_expr('create_date')} AS legacy_create_date,
                   {source_expr('write_uid')} AS legacy_write_uid,
                   {source_expr('write_date')} AS legacy_write_date
              FROM {source_table} s
              JOIN res_partner p ON p.id = s.x_res_partner_id
             ORDER BY s.id
            """
        )
        studio_rows = cr.fetchall()
        if not studio_rows:
            return

        # IDs already imported are the authoritative idempotency key.
        cr.execute(
            """
            SELECT legacy_studio_id
              FROM tko_contact_access_data
             WHERE legacy_studio_id IS NOT NULL
            """
        )
        imported_ids = {row[0] for row in cr.fetchall()}

        imported = 0
        skipped_existing = 0
        skipped_incomplete = 0
        for (
            studio_id,
            partner_id,
            platform_id,
            login,
            clear_password,
            legacy_description,
            legacy_notes,
            legacy_sequence,
            legacy_create_uid,
            legacy_create_date,
            legacy_write_uid,
            legacy_write_date,
        ) in studio_rows:
            if studio_id in imported_ids:
                skipped_existing += 1
                continue

            platform = (platform_names.get(platform_id) or "").strip()
            login = (self._studio_scalar_text(login) or "").strip()
            clear_password = self._studio_scalar_text(clear_password) or ""
            legacy_description = self._studio_scalar_text(legacy_description)
            legacy_notes = self._studio_scalar_text(legacy_notes)

            if not platform or not login or not clear_password:
                skipped_incomplete += 1
                continue

            encrypted_password = encrypt_secret(clear_password)
            create_uid = legacy_create_uid or legacy_write_uid or 1
            write_uid = legacy_write_uid or create_uid
            create_date = legacy_create_date or legacy_write_date or fields.Datetime.now()
            write_date = legacy_write_date or create_date

            cr.execute(
                """
                INSERT INTO tko_contact_access_data (
                    partner_id,
                    site,
                    username,
                    password_encrypted,
                    password_set_uid,
                    password_set_at,
                    legacy_studio_id,
                    legacy_studio_description,
                    legacy_studio_notes,
                    legacy_studio_sequence,
                    create_uid,
                    create_date,
                    write_uid,
                    write_date
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    partner_id,
                    platform,
                    login,
                    encrypted_password,
                    write_uid,
                    write_date,
                    studio_id,
                    legacy_description,
                    legacy_notes,
                    legacy_sequence,
                    create_uid,
                    create_date,
                    write_uid,
                    write_date,
                ),
            )
            if cr.rowcount:
                imported_ids.add(studio_id)
                imported += 1
            else:
                skipped_existing += 1

        # Normalise metadata of records that may already have been imported
        # by an earlier v15 build/workaround. This does not touch the encrypted
        # password and keeps the migration idempotent.
        cr.execute(
            f"""
            SELECT a.id,
                   s.x_studio_plataforma,
                   {source_expr('x_name')} AS legacy_description,
                   {source_expr('x_studio_notas')} AS legacy_notes,
                   {source_expr('x_studio_sequence')} AS legacy_sequence
              FROM tko_contact_access_data a
              JOIN {source_table} s ON s.id = a.legacy_studio_id
             WHERE a.legacy_studio_id IS NOT NULL
            """
        )
        for access_id, platform_id, description, notes, sequence in cr.fetchall():
            platform = (platform_names.get(platform_id) or "").strip()
            description = self._studio_scalar_text(description)
            notes = self._studio_scalar_text(notes)
            cr.execute(
                """
                UPDATE tko_contact_access_data
                   SET site = CASE WHEN %s <> '' THEN %s ELSE site END,
                       legacy_studio_description = %s,
                       legacy_studio_notes = %s,
                       legacy_studio_sequence = %s
                 WHERE id = %s
                """,
                (platform, platform, description, notes, sequence, access_id),
            )

        if imported or skipped_incomplete:
            _logger.info(
                "Studio Dados de Acesso migration: imported=%s, already_imported=%s, "
                "incomplete_left_in_studio=%s",
                imported,
                skipped_existing,
                skipped_incomplete,
            )

    def _sync_legacy_observations(self):
        """Preserve pre-existing Studio notes when the new text field is empty."""
        self.env.cr.execute("""
            UPDATE tko_contact_access_data
               SET observations = BTRIM(REGEXP_REPLACE(
                   REGEXP_REPLACE(legacy_studio_notes, '<[^>]+>', ' ', 'g'),
                   '[[:space:]]+', ' ', 'g'))
             WHERE observations IS NULL AND legacy_studio_notes IS NOT NULL
        """)

    def init(self):
        """Synchronize catalog after SQL model tables are fully initialized."""
        self._sync_existing_platforms()
        self._sync_legacy_observations()

    def _sync_existing_platforms(self):
        """Backfill existing dropdown values without modifying credentials.

        SQL is deliberately used during schema upgrades because ORM create
        permission checks and cross-model initialisation may not be complete.
        """
        cr = self.env.cr
        cr.execute("SELECT to_regclass('tko_contact_access_platform')")
        if not cr.fetchone()[0]:
            return
        cr.execute("""
            SELECT DISTINCT BTRIM(site)
            FROM tko_contact_access_data
            WHERE COALESCE(BTRIM(site), '') <> ''
        """)
        for (name,) in cr.fetchall():
            cr.execute("""
                INSERT INTO tko_contact_access_platform (name, active, create_date, write_date)
                SELECT %s, TRUE, NOW(), NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM tko_contact_access_platform WHERE LOWER(name) = LOWER(%s)
                )
            """, (name, name))
        cr.execute("""
            UPDATE tko_contact_access_data a
               SET platform_id = p.id
              FROM tko_contact_access_platform p
             WHERE LOWER(BTRIM(a.site)) = LOWER(p.name)
               AND (a.platform_id IS NULL OR a.platform_id <> p.id)
        """)

    @api.model
    def _is_superuser_context(self):
        # Only an explicit sudo/superuser environment bypasses the business
        # permission matrix. A normal Odoo administrator (base.group_system)
        # must be granted View/Create/Edit/Delete exactly like any other user.
        return bool(self.env.su)

    @api.model
    def _has_company_permission(self, permission):
        if self._is_superuser_context():
            return True
        return self.env.company._security_password_user_has_permission(
            self.env.user, permission
        )

    @api.model
    def _can_view(self):
        return self._has_company_permission("view")

    @api.model
    def _can_create(self):
        return self._has_company_permission("create")

    @api.model
    def _can_edit(self):
        return self._has_company_permission("write")

    @api.model
    def _can_delete(self):
        return self._has_company_permission("delete")

    @api.model
    def _require_view(self):
        if not self._can_view():
            raise AccessError(_("Não tem permissão para visualizar esta Password."))

    @api.model
    def _require_create(self):
        if not self._can_create():
            raise AccessError(_("Não tem permissão para definir uma nova Password."))

    @api.model
    def _require_delete(self):
        if not self._can_delete():
            raise AccessError(_("Não tem permissão para apagar este Dado de Acesso e a respetiva Password."))

    def _require_edit(self):
        # Editing an existing Dados de Acesso row is deliberately strict.
        # CREATE permission never implies EDIT permission, including for the
        # creator. EDIT applies to Plataforma, Login and Password alike.
        if not self._can_edit():
            raise AccessError(_(
                "Não tem permissão para editar este Dado de Acesso. "
                "A permissão Editar é necessária para alterar Plataforma, "
                "Login ou Password."
            ))


    def _audit_post(self, title, text, action="change"):
        """Append a protected history row, never publish to the normal chatter."""
        self.ensure_one()
        self.env["tko.contact.access.audit"].sudo().create({
            "partner_id": self.partner_id.id,
            "access_data_id": self.id,
            "platform": self.site or "",
            "actor_id": self.env.uid,
            "action": action,
            "title": title,
            "details": text,
            "occurred_at": fields.Datetime.now(),
        })

    def _field_labels_for_log(self, vals):
        label_map = {
            "site": _("Plataforma"),
            "platform_id": _("Plataforma"),
            "observations": _("Observações"),
            "url": _("URL"),
            "username": _("Login"),
            "password": _("Password"),
        }
        return list(dict.fromkeys(
            label_map[name]
            for name in ("site", "platform_id", "url", "username", "observations", "password")
            if name in vals
        ))

    @api.model
    def _prepare_encrypted_password_vals(self, vals):
        """Translate the clear-text UI field to the encrypted DB field.

        An explicitly supplied empty password is always rejected. This avoids
        both clearing a password and the previous behaviour where an empty
        value could be silently ignored.
        """
        vals = dict(vals)
        if "password" not in vals:
            return vals

        clear_password = vals.pop("password")
        if clear_password in (False, None, ""):
            raise ValidationError(_("A Password é obrigatória e não pode ficar vazia."))

        vals["password_encrypted"] = encrypt_secret(clear_password)
        vals["password_set_uid"] = self.env.user.id
        vals["password_set_at"] = fields.Datetime.now()
        return vals

    @api.model
    def _reject_direct_secret_field_write(self, vals):
        """Do not let normal RPC clients write encryption/audit internals.

        Users create/change passwords through the public ``password`` field;
        only the model itself may translate that to encrypted storage.
        """
        protected = {"password_encrypted", "password_set_uid", "password_set_at"}
        if (
            not self.env.su
            and not self.env.context.get("_advicebiz_password_inverse")
            and protected.intersection(vals)
        ):
            raise AccessError(_("Os campos internos de segurança não podem ser alterados diretamente."))

    @api.model
    def _normalize_platform(self, vals):
        vals = dict(vals)
        if "platform_id" in vals:
            platform = self.env["tko.contact.access.platform"].browse(
                vals["platform_id"] or 0
            ).exists()
            if not platform:
                raise ValidationError(_("É necessário escolher uma Plataforma válida."))
            vals["site"] = platform.name
        elif "site" in vals and vals["site"]:
            # Keep API consumers and Studio migration backwards compatible.
            site = vals["site"].strip()
            platform = self.env["tko.contact.access.platform"].sudo().search(
                [("name", "=ilike", site)], limit=1
            )
            if not platform:
                platform = self.env["tko.contact.access.platform"].sudo().create({"name": site})
            vals["platform_id"] = platform.id
        return vals

    @api.model
    def _normalize_visible_values(self, vals):
        """Trim Plataforma/Login while preserving passwords byte-for-byte."""
        vals = dict(vals)
        for field_name in ("site", "username"):
            if field_name in vals and isinstance(vals[field_name], str):
                vals[field_name] = vals[field_name].strip()
        return vals

    @api.model
    def _validate_required_values_for_create(self, vals):
        if not vals.get("site"):
            raise ValidationError(_("A Plataforma é obrigatória e não pode ficar vazia."))
        if not vals.get("username"):
            raise ValidationError(_("O Login é obrigatório e não pode ficar vazio."))
        if not vals.get("password_encrypted"):
            raise ValidationError(_("A Password é obrigatória e não pode ficar vazia."))

    def _validate_required_values_for_write(self, vals):
        """Prevent clearing any of the three visible access-data fields."""
        for record in self:
            site = vals.get("site", record.site)
            username = vals.get("username", record.username)
            encrypted_password = vals.get(
                "password_encrypted", record.password_encrypted
            )
            if not site:
                raise ValidationError(_("A Plataforma é obrigatória e não pode ficar vazia."))
            if not username:
                raise ValidationError(_("O Login é obrigatório e não pode ficar vazio."))
            if not encrypted_password:
                raise ValidationError(_("A Password é obrigatória e não pode ficar vazia."))

    @api.model_create_multi
    def create(self, vals_list):
        # Access to the contact/tab is unrestricted by the password matrix.
        # A complete new credential still needs CREATE permission because its
        # mandatory initial password is being stored here.
        self._require_create()

        prepared = []
        for incoming in vals_list:
            self._reject_direct_secret_field_write(incoming)
            vals = self._normalize_platform(self._normalize_visible_values(incoming))
            vals = self._prepare_encrypted_password_vals(vals)
            self._validate_required_values_for_create(vals)

            partner = self.env["res.partner"].browse(vals.get("partner_id")).exists()
            if not partner:
                raise AccessError(_("É necessário indicar um contacto válido."))

            partner.check_access("write")
            prepared.append(vals)

        records = super().create(prepared)

        for record in records:
            record._audit_post(
                _("Dado de Acesso criado"),
                _('Foi criado um Dado de Acesso para "%s".') % (record.site or ""),
                action="create",
            )

        return records

    def write(self, vals):
        # EDIT permission governs the complete existing row: Plataforma, Login
        # and Password. It does not affect opening the contact or viewing the
        # Dados de Acesso tab.
        self._require_edit()

        for partner in self.partner_id:
            partner.check_access("write")

        self._reject_direct_secret_field_write(vals)
        incoming_vals = self._normalize_platform(self._normalize_visible_values(vals))
        changed_labels = self._field_labels_for_log(incoming_vals)

        if not self.env.context.get("_advicebiz_password_inverse"):
            vals = self._prepare_encrypted_password_vals(incoming_vals)
        else:
            vals = dict(incoming_vals)

        self._validate_required_values_for_write(vals)
        result = super().write(vals)

        if changed_labels:
            changed = ", ".join(changed_labels)
            for record in self:
                record._audit_post(
                    _("Dado de Acesso alterado"),
                    _('O Dado de Acesso de "%s" foi alterado. Campos: %s.')
                    % (record.site or "", changed),
                    action="change",
                )

        return result

    def unlink(self):
        # Deleting the credential also deletes its encrypted password, so this
        # is the one row-level operation governed by the DELETE password right.
        self._require_delete()

        audit_data = []
        actor_id = self.env.uid
        for record in self:
            record.partner_id.check_access("write")
            audit_data.append((record.partner_id.id, record.site or ""))

        result = super().unlink()
        Audit = self.env["tko.contact.access.audit"].sudo()
        for partner_id, site in audit_data:
            Audit.create({
                "partner_id": partner_id,
                "platform": site,
                "actor_id": actor_id,
                "action": "delete",
                "title": _("Dado de Acesso apagado"),
                "details": _('Foi apagado o Dado de Acesso de "%s".') % site,
                "occurred_at": fields.Datetime.now(),
            })
        return result

    def _reveal_password_for_authorized_request(self):
        """Decrypt one password for the protected HTTP reveal endpoint only."""
        self.ensure_one()
        self._require_view()
        self.partner_id.check_access("read")

        clear_password = decrypt_secret(self.password_encrypted)
        if clear_password:
            self._audit_post(
                _("Palavra-passe visualizada"),
                _('Foi visualizada a palavra-passe de "%s".') % (self.site or ""),
                action="reveal",
            )
        return clear_password or ""
