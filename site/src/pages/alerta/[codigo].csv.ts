import type { APIRoute } from "astro";
import { type Alerta, alertaPlano, alertas, csv } from "../../lib/dados";

export function getStaticPaths() {
  return alertas().map((a) => ({ params: { codigo: a.codigo }, props: { alerta: a } }));
}

export const GET: APIRoute = ({ props }) =>
  new Response(csv([alertaPlano((props as { alerta: Alerta }).alerta)]), {
    headers: { "Content-Type": "text/csv; charset=utf-8" },
  });
