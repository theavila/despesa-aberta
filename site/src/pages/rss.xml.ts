import rss from "@astrojs/rss";
import type { APIContext } from "astro";
import { alertas, meta, reais, TRATAMENTO, url } from "../lib/dados";

export function GET(context: APIContext) {
  const m = meta();
  return rss({
    title: m.site.nome,
    description: `Alertas de gastos atípicos de parlamentares federais. ${m.aviso}`,
    site: new URL(url(), context.site).toString(),
    customData: "<language>pt-BR</language>",
    items: alertas().slice(0, 50).map((a) => ({
      title: `${a.codigo}: ${TRATAMENTO[a.casa]} ${a.parlamentar_nome} — ${reais(a.valor)} (${a.regra_nome})`,
      link: url(`alerta/${a.codigo}/`),
      pubDate: new Date(`${a.criado_em}Z`),
      description: `${a.detalhe} ${m.aviso}`,
    })),
  });
}
