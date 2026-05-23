# Tank — Issue #105 Cost Guardrails

**Timestamp:** 2026-05-22T16:01:10-04:00  
**Author:** Tank  
**Status:** Implemented in PR branch `squad/105-cost-guardrails`

## Change

- Set Container Apps dev floor to `minReplicas=0` in `infra/modules/container-app.bicep` so the app can scale to zero when idle.
- Added budget-specific parameter plumbing in `infra/main.bicep` (`budgetAlertEmail`) so RG budget alerts can be provisioned without also enabling unrelated Azure Monitor alert rules.
- Set the dev budget default to `$25/month` and wired `infra/main.bicepparam` to notify Manish at `marora@gmail.com`.
- Updated `infra/modules/budget.bicep` notifications to 50%, 80%, and 100% actual cost.
- Documented budget recreation and manual scale-to-zero verification commands in `infra/README.md`.

## Dormant-cost lesson framing

The threshold is intentionally low. The dormant-cost lesson showed idle infrastructure can burn hundreds of dollars when provisioned capacity stays alive; a $25/month RG alert catches that class of drift within days rather than weeks.

## Deployment notes

- Existing dev resource group is `transpose-sc` (not `transpose-dev-rg` in the ticket text); deployment and verification targeted the live `transpose-dev-app` there.
- Targeted module what-if was used to avoid unrelated full-stack drift from the root template.
- Applying `minReplicas=0` created revision `transpose-dev-app--0000009`; Container Apps treats template scale as revision-scoped. Image digest stayed unchanged from Step 7.
- Budget `transpose-dev-monthly-budget` is visible via `az consumption budget list --resource-group transpose-sc`.

## Foundry #102

Not folded in. The live Foundry Agent is present (`Microsoft.App/agents/transpose-sc-agent`), but #102 requires bringing the agent under IaC lifecycle plus dormancy policy. There is no safe single `provisioned=false` toggle in current infra.

## Post-merge verification plan

- After the app is idle for 10–15 minutes, run `az containerapp replica list --resource-group transpose-sc --name transpose-dev-app --revision <active-revision>` and expect `[]`.
- Confirm App Insights receives telemetry after the next cold start / health probe.
- Confirm Manish receives budget email when actual cost crosses 50%, 80%, and 100% of $25.
