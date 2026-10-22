import type { APIRoute } from "astro";
import { alertaPlano, alertasPorCodigo, csv, type Parlamentar, parlamentares } from "../../lib/dados";

export function getStaticPaths() {
  return parlamentares().map((p) => ({ params: { chave: p.chave }, props: { p } }));
}

// CSV com o total por categoria; os alertas seguem em linhas próprias quando houver.
export const GET: APIRoute = ({ props }) => {
  const { p } = props as { p: Parlamentar };
  const porCodigo = alertasPorCodigo();
  const categorias = p.por_categoria.map((c) => ({
    tipo: "total_categoria", parlamentar: p.nome, casa: p.casa, categoria: c.categoria, total: c.total,
  }));
  const alertas = p.alertas.map((c) => alertaPlano(porCodigo.get(c)!));
  const corpo = csv(categorias) + (alertas.length ? "\n" + csv(alertas) : "");
  return new Response(corpo, { headers: { "Content-Type": "text/csv; charset=utf-8" } });
};
