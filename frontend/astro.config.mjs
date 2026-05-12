import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";

export default defineConfig({
  integrations: [tailwind()],
  site: "https://energy-template.vbartalis.dev",
  output: "static",
  trailingSlash: "ignore",
});