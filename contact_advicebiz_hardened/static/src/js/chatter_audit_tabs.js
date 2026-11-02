/** @odoo-module **/

import { Chatter } from "@mail/chatter/web_portal/chatter";
import { patch } from "@web/core/utils/patch";
import { onWillUpdateProps, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

// The backend chatter reuses mail.Chatter from web_portal, extended by mail's
// web patch. This extension affects partner threads only.
patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        this.advicebizAudit = useState({
            activeTab: "messages",
            rows: [],
            loading: false,
            error: false,
            hasMore: false,
            offset: 0,
            partnerId: null,
            generation: 0,
        });
        onWillUpdateProps((nextProps) => {
            if (nextProps.threadId !== this.props.threadId || nextProps.threadModel !== this.props.threadModel) {
                this.advicebizAudit.generation += 1;
                this.advicebizAudit.partnerId = null;
                this.advicebizAudit.activeTab = "messages";
                this.advicebizAudit.rows = [];
                this.advicebizAudit.loading = false;
                this.advicebizAudit.error = false;
                this.advicebizAudit.hasMore = false;
                this.advicebizAudit.offset = 0;
            }
        });
    },

    get advicebizIsPartnerChatter() {
        return this.props.threadModel === "res.partner" && Number(this.props.threadId) > 0;
    },

    // Referenced directly by Owl event handlers so Owl binds the Chatter
    // instance. Inline arrow closures in a template do not bind this when
    // passing an extracted method name (the previous source of TypeError).
    advicebizShowMessages() {
        return this.advicebizOpenAudit("messages");
    },

    advicebizShowAudit() {
        return this.advicebizOpenAudit("audit");
    },

    async advicebizOpenAudit(tab) {
        if (tab === "messages") {
            this.advicebizAudit.activeTab = "messages";
            return;
        }
        if (!this.advicebizIsPartnerChatter) {
            return;
        }
        this.advicebizAudit.activeTab = "audit";
        if (this.advicebizAudit.partnerId !== Number(this.props.threadId)) {
            this.advicebizAudit.rows = [];
            this.advicebizAudit.offset = 0;
            this.advicebizAudit.hasMore = false;
        }
        await this.advicebizRefreshAudit();
    },

    async advicebizRefreshAudit() {
        if (!this.advicebizIsPartnerChatter) {
            return;
        }
        this.advicebizAudit.rows = [];
        this.advicebizAudit.offset = 0;
        this.advicebizAudit.hasMore = false;
        await this.advicebizLoadAudit();
    },

    async advicebizLoadAudit() {
        if (!this.advicebizIsPartnerChatter || this.advicebizAudit.loading) {
            return;
        }
        const partnerId = Number(this.props.threadId);
        const generation = ++this.advicebizAudit.generation;
        const offset = this.advicebizAudit.offset;
        this.advicebizAudit.loading = true;
        this.advicebizAudit.error = false;
        try {
            const result = await rpc("/advicebiz/access_data/audit_list", {
                partner_id: partnerId,
                offset,
                limit: 50,
            });
            if (generation !== this.advicebizAudit.generation ||
                Number(this.props.threadId) !== partnerId) {
                return;
            }
            const entries = result.entries || [];
            this.advicebizAudit.rows = [...this.advicebizAudit.rows, ...entries];
            this.advicebizAudit.offset += entries.length;
            this.advicebizAudit.hasMore = Boolean(result.has_more);
            this.advicebizAudit.partnerId = partnerId;
        } catch (error) {
            if (generation === this.advicebizAudit.generation) {
                this.advicebizAudit.error = true;
            }
            // Avoid noisy repeated notifications; the in-place error is visible.
        } finally {
            if (generation === this.advicebizAudit.generation) {
                this.advicebizAudit.loading = false;
            }
        }
    },
});
