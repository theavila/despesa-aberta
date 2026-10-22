import type { APIRoute } from "astro";
import { type Alerta, alertas } from "../../lib/dados";

export function getStaticPaths() {
  return alertas().map((a) => ({ params: { codigo: a.codigo }, props: { alerta: a } }));
}

export const GET: APIRoute = ({ props }) =>
  new Response(JSON.stringify((props as { alerta: Alerta }).alerta, null, 1), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
