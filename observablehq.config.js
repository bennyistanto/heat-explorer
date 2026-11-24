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
  // visitor counts with Google Analytics; the tag loads from Google, the only third-party request the page makes
  // the flame of the page title as the browser tab icon, written inline so no extra file is fetched
  head: `<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg%20xmlns=%22http://www.w3.org/2000/svg%22%20viewBox=%220%200%2024%2024%22%3E%3Cpath%20d=%22M12.6%201.5c.5%203-1%204.800-2.700%206.600C8%2010.100%206%2012.100%206%2015.300A6%206%200%200%200%2012%2021.500a6%206%200%200%200%206-6.200c0-2.300-1-4-2.100-5.400-.300%201.500-1%202.500-2%203.100.400-3.600-.300-7.800-1.300-11.500Z%22%20fill=%22%23d9783c%22/%3E%3Cpath%20d=%22M12%2021.500a3.300%203.300%200%200%201-3.300-3.400c0-1.700%201.100-2.700%202.100-3.800.600-.700%201.100-1.400%201.200-2.400%201.800%201.600%203.300%203.600%203.300%206.200A3.300%203.300%200%200%201%2012%2021.500Z%22%20fill=%22%2374290c%22/%3E%3C/svg%3E">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-FD4Q7PHZ2E"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag("js", new Date());
  gtag("config", "G-FD4Q7PHZ2E");
</script>`,
  globalStylesheets: [], // no font download from a third party: the page uses the visitor's system fonts
  footer: "Heat data: AgERA5, Copernicus Climate Change Service (DOI 10.24381/cds.6c68c9bb). Boundaries: FieldMaps Global Edge-matched Subnational Boundaries and OpenStreetMap contributors, under the Open Database License 1.0. Built with Observable Framework. Developed by <a href=\"https://benny.istan.to\" target=\"_blank\" rel=\"noopener\">Benny Istanto</a> as a casual-weekend project. Repo is accessible from <a href=\"https://github.com/bennyistanto/heat-explorer\" target=\"_blank\" rel=\"noopener\">https://github.com/bennyistanto/heat-explorer</a>."
};
