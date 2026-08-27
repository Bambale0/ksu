# Prompt tools pricing

Prompt tools are a paid product surface. They must not default to zero credits because users can copy the generated prompt and run generation outside ROXY.

Default public ROX prices:

| Tool | Price |
| --- | ---: |
| Prompt по описанию | 1 ROX |
| Prompt по фото | 1 ROX |
| Prompt по видео | 30 ROX |

Prompt по описанию and Prompt по фото are fixed product prices and are not overridden by Admin Tariffs `prompt_costs`; this keeps the customer price stable across model/provider routing changes. Admins can still get an effective zero charge through admin billing access, but the catalog exposes `retail_cost_credits` so the Mini App can show the public user price.
