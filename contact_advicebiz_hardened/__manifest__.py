{
    "name": "Contact | Advicebiz - Dados de Acesso Hardened",
    "version": "19.0.3.17.4",
    "summary": "Dados de acesso autónomos, cifrados, com permissões separadas e auditoria",
    "category": "Contacts",
    "author": "Advicebiz",
    "license": "LGPL-3",
    "depends": [
        "base",
        "contacts",
        "mail",
        "web",
        "security_password_hardened",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/contact_views.xml",
        "views/access_platform_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "contact_advicebiz_hardened/static/src/js/click_reveal_password.js",
            "contact_advicebiz_hardened/static/src/xml/click_reveal_password.xml",
            "contact_advicebiz_hardened/static/src/css/access_data.css",
            "contact_advicebiz_hardened/static/src/js/chatter_audit_tabs.js",
            "contact_advicebiz_hardened/static/src/xml/chatter_audit_tabs.xml",
            "contact_advicebiz_hardened/static/src/css/chatter_audit_tabs.css",
        ],
    },
    "external_dependencies": {"python": ["cryptography"]},
    "installable": True,
    "application": False,
}
