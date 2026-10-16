# Commercial source-code policy and distribution choices

**Status: documented for owner decision — no licensing or repository-visibility change made.**

The Bar–Hotel–Retail POS is intended to be a commercially distributed, configurable system serving independent shops, hotels, restaurants and other businesses. Commercial distribution and public-source collaboration require separate decisions.

## Current observed policy

- As examined on 16 October 2026, no root `LICENSE`, `COPYING` or EULA file was present in the source tree. **The absence of a license is not an open-source license.** Default copyright generally applies. GitHub's terms nevertheless allow viewing and forking a public repository; lack of a license alone does not keep source confidential.
- The owner has **not** authorized changing repository visibility, granting redistribution rights, or adding a license through this roadmap. Leave these settings unchanged until an explicit future business decision.
- The repository can contain third-party packages with separate obligations. Retaining one's own copyright does not override dependency or bundled asset licenses; audit Python, JavaScript, icons, fonts, themes and any images before sale.

## Choices to make before selling code or installers

| Distribution strategy | Advantages | Trade-offs |
| --- | --- | --- |
| Closed-source hosted SaaS (recommended evaluation baseline) | Centralized upgrades, multi-tenant security fixes, controlled deployment and subscriptions | Requires reliable hosting, backups, incident response and an acceptable service agreement |
| Proprietary on-premise installer/server package | Customers keep installations under their control | Licensing, update delivery, client support, source disclosure protections and hardware dependencies need attention |
| Open-source core plus paid hosting/support | Community collaboration and broader ecosystem | License selection, source/public obligations and contribution rights require deliberate legal review |
| Full open-source license | Clearly permits defined third-party uses | Must accept the freedoms and compliance consequences of the selected license |

**No option has been elected by this document.** Do not label the software “open source” merely because repository contents may be visible online.

## Suggested owner decision checklist

- Record the company/legal entity that owns this code and whether contributor rights are assigned/licensed.
- Select deployment model, source availability and permissions for customers, resellers and contractors.
- Obtain Uganda-relevant professional advice on customer contracts, tax/fiscal integration duties, privacy/data protection, warranty, liability and export distribution.
- If choosing proprietary distribution, draft an appropriate EULA and service terms reviewed by qualified counsel. These should cover number of installations/users, payment/subscriptions, upgrades, hardware drivers, support, data ownership, refunds, security patches, outage handling and termination.
- If planning to keep source nonpublic, consider private repository access, protected branches, mandatory MFA, rotating leaked secrets, and audit of historical forks/clones. **Making a once-public repository private does not retract existing clones or public forks.**
- Inventory all third-party components/linked services and confirm attribution, permitted distribution and disclosure requirements.
- Preserve distinct terms for source-code licensing, SaaS subscription, equipment sales and customer data processing; they are not interchangeable.
- Record version/date of every actual policy change separately. Do not claim a proprietary EULA is in effect without publishing and accepting an approved text.

## Current safe interim rules

- Do not insert a new OSS license, license grant or EULA into the product without owner approval.
- Do not change GitHub visibility automatically. Source visibility and customer access are separate operational decisions.
- Keep real customer records, provider credentials, payment details and production environment variables out of this repository.
- Continue to secure the application even if the code remains publicly visible, and do not rely on source secrecy for authentication or authorization.

Sources consulted:
- GitHub: [Licensing a repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)
- GitHub: [Setting repository visibility](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)
- Choose a License: [No License](https://choosealicense.com/no-permission/)

This is a product-governance document, not legal advice or a change of ownership or license.
