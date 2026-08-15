import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const [html, css, script, compose, config] = await Promise.all([
  readFile("web/site/index.html", "utf8"),
  readFile("web/site/styles.css", "utf8"),
  readFile("web/site/app.js", "utf8"),
  readFile("docker-compose.yml", "utf8"),
  readFile("litellm/config.yaml", "utf8"),
]);

assert.match(html, /id="base-url"/);
assert.match(html, /id="health-label"/);
assert.match(html, /href="\/ui\/"/);
assert.match(script, /window\.location\.origin.*\/cursor/);
assert.match(script, /\/health\/readiness/);
assert.match(css, /@media \(max-width: 720px\)/);
assert.match(compose, /litellm-database:v1\.97\.0-rc\.1/);
assert.match(compose, /postgres:16-alpine/);
assert.match(compose, /"3029:80"/);
assert.match(config, /store_model_in_db: true/);

console.log("Static contracts passed");
