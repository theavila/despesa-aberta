import type { APIRoute } from "astro";
import { alertasPorCodigo, type Parlamentar, parlamentares } from "../../lib/dados";

export function getStaticPaths() {
  return parlamentares().map((p) => ({ params: { chave: p.chave }, props: { p } }));
}

export const GET: APIRoute = ({ props }) => {
  const { p } = props as { p: Parlamentar };
  const porCodigo = alertasPorCodigo();
  const corpo = { ...p, alertas: p.alertas.map((c) => porCodigo.get(c)) };
  return new Response(JSON.stringify(corpo, null, 1), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
};
