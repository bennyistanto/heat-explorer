// Observable Framework configuration. Source root is site/, build output is dist/.
// Framework generates relative links, so the built site works under /heat-explorer/ on GitHub Pages.
export default {
  root: "site",
  output: "dist",
  title: "Heat Explorer",
  theme: ["air", "alt", "wide"], // light only: the map colours are chosen against a light surface
  sidebar: false,
  toc: false,
  pager: false,
  pages: [],
  globalStylesheets: [], // no font download from a third party: the page uses the visitor's system fonts
  footer: "Heat data: AgERA5, Copernicus Climate Change Service (DOI 10.24381/cds.6c68c9bb). Boundaries: FieldMaps Global Edge-matched Subnational Boundaries and OpenStreetMap contributors, under the Open Database License 1.0. Built with Observable Framework. Developed by <a href=\"https://benny.istan.to\" target=\"_blank\" rel=\"noopener\">Benny Istanto</a> as a casual-weekend project. Repo is accessible from <a href=\"https://github.com/bennyistanto/heat-explorer\" target=\"_blank\" rel=\"noopener\">https://github.com/bennyistanto/heat-explorer</a>."
};
