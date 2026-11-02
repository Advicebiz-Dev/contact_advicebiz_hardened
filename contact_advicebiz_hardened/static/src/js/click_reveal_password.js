/** @odoo-module **/

import { Component, onMounted, useRef, useState, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { Dialog } from "@web/core/dialog/dialog";
import { CharField, charField } from "@web/views/fields/char/char_field";

class ManualReauthDialog extends Component {
    static template = xml`
        <Dialog title="'Confirmar identidade'">
            <div class="mb-2">
                <label class="form-label">
                    Introduza manualmente a sua palavra-passe do Odoo para revelar esta password.
                </label>
                <input type="password"
                       class="form-control"
                       name="advicebiz_manual_reauth_password"
                       autocomplete="new-password"
                       data-lpignore="true"
                       data-1p-ignore="true"
                       data-form-type="other"
                       t-ref="passwordInput"
                       t-model="state.password"
                       t-on-keydown="onKeydown"
                       placeholder="Palavra-passe do Odoo"/>
            </div>
            <t t-set-slot="footer">
                <button class="btn btn-primary"
                        t-att-disabled="state.busy || !state.password"
                        t-on-click="confirm">
                    Confirmar
                </button>
                <button class="btn btn-secondary"
                        t-att-disabled="state.busy"
                        t-on-click="props.close">
                    Cancelar
                </button>
            </t>
        </Dialog>
    `;
    static components = { Dialog };
    static props = {
        close: Function,
        onConfirm: Function,
    };

    setup() {
        this.state = useState({ password: "", busy: false });
        this.passwordInput = useRef("passwordInput");

        onMounted(() => {
            // Password managers and browsers must never pre-fill the Odoo
            // re-authentication secret. Clear both Owl state and the DOM a few
            // times after mount because some managers inject asynchronously.
            const clear = () => {
                this.state.password = "";
                if (this.passwordInput.el) {
                    this.passwordInput.el.value = "";
                }
            };
            clear();
            setTimeout(clear, 50);
            setTimeout(clear, 200);
        });
    }

    async confirm() {
        if (this.state.busy || !this.state.password) {
            return;
        }
        this.state.busy = true;
        const typedPassword = this.state.password;
        try {
            const ok = await this.props.onConfirm(typedPassword);
            this.state.password = "";
            if (this.passwordInput.el) {
                this.passwordInput.el.value = "";
            }
            if (ok) {
                this.props.close();
            }
        } finally {
            this.state.busy = false;
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.confirm();
        }
    }
}

class ChangePasswordDialog extends Component {
    static template = xml`
        <Dialog title="'Alterar password'">
            <p class="mb-3">
                Confirmar alteração de password para
                <strong>Plataforma <t t-esc="props.platform || '-'"/></strong>
                e
                <strong>Login <t t-esc="props.login || '-'"/></strong>?
            </p>
            <div class="mb-2">
                <label class="form-label">Nova password</label>
                <input type="password"
                       class="form-control"
                       name="advicebiz_new_access_password"
                       autocomplete="new-password"
                       data-lpignore="true"
                       data-1p-ignore="true"
                       data-form-type="other"
                       t-ref="newPasswordInput"
                       t-model="state.password"
                       t-on-keydown="onKeydown"
                       placeholder="Introduza a nova password"/>
            </div>
            <t t-set-slot="footer">
                <button class="btn btn-primary"
                        t-att-disabled="state.busy || !state.password"
                        t-on-click="confirm">
                    Confirmar alteração
                </button>
                <button class="btn btn-secondary"
                        t-att-disabled="state.busy"
                        t-on-click="props.close">
                    Cancelar
                </button>
            </t>
        </Dialog>
    `;
    static components = { Dialog };
    static props = {
        close: Function,
        onConfirm: Function,
        platform: { type: String, optional: true },
        login: { type: String, optional: true },
    };

    setup() {
        this.state = useState({ password: "", busy: false });
        this.newPasswordInput = useRef("newPasswordInput");
        onMounted(() => {
            const clearAndFocus = () => {
                this.state.password = "";
                if (this.newPasswordInput.el) {
                    this.newPasswordInput.el.value = "";
                    this.newPasswordInput.el.focus();
                }
            };
            clearAndFocus();
            setTimeout(clearAndFocus, 50);
        });
    }

    async confirm() {
        if (this.state.busy || !this.state.password) {
            return;
        }
        this.state.busy = true;
        try {
            const ok = await this.props.onConfirm(this.state.password);
            if (ok) {
                this.state.password = "";
                this.props.close();
            }
        } finally {
            this.state.busy = false;
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.confirm();
        }
    }
}

export class ClickRevealPasswordField extends CharField {
    static template = "contact_advicebiz_hardened.ClickRevealPasswordField";

    setup() {
        super.setup();
        this.notification = useService("notification");
        this.dialogService = useService("dialog");
        this.storedInput = useRef("storedInput");
        this.reveal = useState({ visible: false, busy: false, plainText: "" });
        this.serverState = useState({
            hasStoredValue: Boolean(this.props.record.data.password_is_set),
        });
    }

    get isExistingRecord() {
        return Boolean(this.props.record.resId);
    }

    get hasDraftValue() {
        return Boolean(this.props.record.data[this.props.name]);
    }

    get hasStoredValue() {
        return Boolean(this.props.record.data.password_is_set) || this.serverState.hasStoredValue;
    }

    get hasValue() {
        return this.hasDraftValue || this.hasStoredValue;
    }

    get maskedValue() {
        return this.hasValue ? "••••••••" : "";
    }

    get revealTitle() {
        return this.reveal.visible
            ? _t("Ocultar palavra-passe")
            : _t("Ver palavra-passe");
    }

    get canCopy() {
        // Copy is intentionally available only after a STORED password has
        // been successfully revealed following Odoo re-authentication.
        return this.isExistingRecord && this.reveal.visible && Boolean(this.reveal.plainText);
    }

    get canViewPassword() {
        return Boolean(this.props.record.data.can_view_password);
    }

    get canEditExisting() {
        return Boolean(this.props.record.data.can_edit_record);
    }

    get canModifyFields() {
        return Boolean(this.props.record.data.can_modify_fields);
    }

    get platformLabel() {
        return this.props.record.data.site || "";
    }

    get loginLabel() {
        return this.props.record.data.username || "";
    }

    stopMouseEvent(ev) {
        // Prevent the editable list from consuming the first click merely to
        // activate/focus the cell. Eye/edit/copy buttons must act immediately.
        ev.preventDefault();
        ev.stopPropagation();
    }

    _syncStoredInput() {
        // Keep ONE persistent DOM input for existing records. This fixes the
        // editable-list issue where replacing the input node was only painted
        // after a second click/focus on the cell.
        const input = this.storedInput.el;
        if (!input) {
            return;
        }
        input.type = this.reveal.visible ? "text" : "password";
        input.value = this.reveal.visible ? this.reveal.plainText : this.maskedValue;
    }

    _hideReveal() {
        this.reveal.visible = false;
        this.reveal.plainText = "";
        this._syncStoredInput();
    }

    _askManualReauth(accessDataId) {
        if (!accessDataId) {
            return Promise.resolve(false);
        }

        return new Promise((resolve) => {
            let settled = false;
            const finish = (value) => {
                if (!settled) {
                    settled = true;
                    resolve(value);
                }
            };

            this.dialogService.add(ManualReauthDialog, {
                onConfirm: async (password) => {
                    try {
                        const result = await rpc("/advicebiz/access_data/check_password", {
                            password,
                            access_data_id: accessDataId,
                        });
                        if (!result?.valid) {
                            const message = result?.reason === "not_authorized"
                                ? _t("Não tem permissão para visualizar esta Password.")
                                : _t("Palavra-passe incorreta. Tente novamente.");
                            this.notification.add(message, { type: "danger" });
                            return false;
                        }
                        finish(true);
                        return true;
                    } catch {
                        this.notification.add(
                            _t("Não foi possível validar a sua palavra-passe do Odoo."),
                            { type: "danger" }
                        );
                        return false;
                    }
                },
            }, {
                onClose: () => finish(false),
            });
        });
    }

    async toggleReveal(ev) {
        ev?.preventDefault();
        ev?.stopPropagation();

        if (this.reveal.busy) {
            return;
        }

        if (this.reveal.visible) {
            this._hideReveal();
            return;
        }

        if (!this.hasValue) {
            return;
        }

        // A brand-new, unsaved row has no server secret yet. Its eye only
        // toggles the password that the user is currently creating locally.
        if (!this.isExistingRecord) {
            if (this.hasDraftValue) {
                this.reveal.visible = true;
            }
            return;
        }

        const resId = this.props.record.resId;
        this.reveal.busy = true;
        try {
            // Every stored-password reveal starts with a fresh, manually typed
            // Odoo password. The server marker authorizes exactly one reveal.
            const authenticated = await this._askManualReauth(resId);
            if (!authenticated) {
                return;
            }

            const result = await rpc("/advicebiz/access_data/reveal_password", {
                access_data_id: resId,
            });
            if (!result?.ok) {
                const message = result?.reason === "reauth_required"
                    ? _t("A confirmação expirou. Clique novamente no olho.")
                    : _t("Não foi possível revelar a palavra-passe.");
                this.notification.add(message, { type: "danger" });
                return;
            }

            this.reveal.plainText = result.password || "";
            this.reveal.visible = Boolean(result.password);

            // Apply the value directly to the persistent input immediately.
            // Owl will also render the same state, but the direct DOM sync
            // guarantees no second click/focus is needed in an editable list.
            this._syncStoredInput();
            requestAnimationFrame(() => this._syncStoredInput());
        } catch {
            this._hideReveal();
            this.notification.add(
                _t("Não foi possível revelar a palavra-passe. Verifique as permissões e a configuração da chave de encriptação."),
                { type: "danger" }
            );
        } finally {
            this.reveal.busy = false;
        }
    }

    openChangePassword(ev) {
        ev?.preventDefault();
        ev?.stopPropagation();
        if (!this.isExistingRecord) {
            return;
        }
        if (!this.canEditExisting) {
            this.notification.add(
                _t("Não tem permissão para alterar esta Password."),
                { type: "danger" }
            );
            return;
        }

        this.dialogService.add(ChangePasswordDialog, {
            platform: this.platformLabel,
            login: this.loginLabel,
            onConfirm: async (newPassword) => {
                try {
                    const result = await rpc("/advicebiz/access_data/change_password", {
                        access_data_id: this.props.record.resId,
                        new_password: newPassword,
                    });
                    if (!result?.ok) {
                        const message = result?.reason === "not_authorized"
                            ? _t("Não tem permissão para alterar esta password.")
                            : _t("Não foi possível alterar a password.");
                        this.notification.add(message, { type: "danger" });
                        return false;
                    }

                    this.serverState.hasStoredValue = true;
                    this._hideReveal();
                    this.notification.add(_t("Password alterada com sucesso."), {
                        type: "success",
                    });
                    return true;
                } catch {
                    this.notification.add(_t("Não foi possível alterar a password."), {
                        type: "danger",
                    });
                    return false;
                }
            },
        });
    }

    async copyPassword(ev) {
        ev?.preventDefault();
        ev?.stopPropagation();
        if (!this.canCopy) {
            return;
        }

        try {
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(this.reveal.plainText);
            } else {
                const area = document.createElement("textarea");
                area.value = this.reveal.plainText;
                area.style.position = "fixed";
                area.style.opacity = "0";
                document.body.appendChild(area);
                area.select();
                document.execCommand("copy");
                area.remove();
            }
            this.notification.add(_t("Password copiada."), { type: "success" });
        } catch {
            this.notification.add(_t("Não foi possível copiar a password."), {
                type: "danger",
            });
        }
    }

    onBlur() {
        // Only the input of a brand-new row is editable through CharField.
        if (!this.isExistingRecord) {
            super.onBlur();
            this.reveal.visible = false;
        }
    }
}

export const clickRevealPasswordField = {
    ...charField,
    component: ClickRevealPasswordField,
    extractProps: (fieldInfo, dynamicInfo) => ({
        ...charField.extractProps(fieldInfo, dynamicInfo),
        isPassword: true,
    }),
};

registry.category("fields").add(
    "advicebiz_click_reveal_password",
    clickRevealPasswordField
);
