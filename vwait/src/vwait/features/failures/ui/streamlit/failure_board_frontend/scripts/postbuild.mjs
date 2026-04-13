import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const indexPath = resolve("dist", "index.html");
const raw = readFileSync(indexPath, "utf-8");
const fixed = raw
  .replaceAll('src="/assets/', 'src="./assets/')
  .replaceAll('href="/assets/', 'href="./assets/');

writeFileSync(indexPath, fixed, "utf-8");
