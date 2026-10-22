// @ts-check
import { defineConfig } from "astro/config";

// Para forks: SITE_URL e BASE_PATH sobrescrevem o endereço do GitHub Pages.
export default defineConfig({
  site: process.env.SITE_URL ?? "https://theavila.github.io",
  base: process.env.BASE_PATH ?? "/despesa-aberta",
  trailingSlash: "ignore",
  build: { format: "directory" },
});
