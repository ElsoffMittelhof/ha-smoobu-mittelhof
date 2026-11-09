/* Run with node tests/test_accounting_date_ui.js */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class HTMLElement {
  constructor() {
    this.shadowRoot = { querySelector: () => null };
  }
  attachShadow() { return this.shadowRoot; }
}
const customElements = { get:()=>false, define() {} };
const source = fs.readFileSync(path.join(__dirname, "../custom_components/smoobu_mittelhof/frontend/mittelhof-accounting-card.js"), "utf8");
const context = { HTMLElement, customElements, Date, Promise, URLSearchParams, console };
const Card = vm.runInNewContext(source + "\nMittelhofAccountingCard;", context);

async function run() {
  const card = new Card();
  const inputs = {
    "[data-from]": { value: "2026-12-01" },
    "[data-to]": { value: "2027-01-31" },
  };
  card.shadowRoot = { querySelector: selector => inputs[selector] || null };
  let apiCalls = [];
  card._api = async (method, route) => {
    apiCalls.push([method, route]);
    if (route.startsWith("search-bookings?")) return {bookings:[],total:0};
    return {records:[]};
  };
  // Simulate the production _render() replacing date input DOM nodes.
  card._render = () => {
    inputs["[data-from]"] = { value: card._from };
    inputs["[data-to]"] = { value: card._to };
  };
  await card._refresh();
  assert.equal(card._from,"2026-12-01");
  assert.equal(card._to,"2027-01-31");
  assert.equal(apiCalls[0][1], "search-bookings?from=2026-12-01&to=2027-01-31");
  assert.equal(inputs["[data-from]"].value, "2026-12-01");
  assert.equal(inputs["[data-to]"].value, "2027-01-31");

  // A later HA state-triggered render must not discard selected dates.
  card._render();
  await card._refresh();
  assert.equal(apiCalls[2][1], "search-bookings?from=2026-12-01&to=2027-01-31");

  inputs["[data-from]"].value="2027-05-01";
  inputs["[data-to]"].value="2027-04-01";
  const before=apiCalls.length;
  await card._refresh();
  assert.equal(apiCalls.length,before);
  assert.match(card._error,/gültigen Zeitraum/);

  inputs["[data-from]"].value="2026-01-01";
  inputs["[data-to]"].value="2028-03-01";
  await card._refresh();
  assert.equal(apiCalls.length,before);
  assert.match(card._error,/731 Tagen/);

  inputs["[data-from]"].value="2026-02-31";
  inputs["[data-to]"].value="2026-03-10";
  await card._refresh();
  assert.equal(apiCalls.length,before);
  assert.match(card._error,/gültigen Zeitraum/);
  console.log("Accounting date selection/re-render regression: OK");
}
run().catch(err=>{console.error(err);process.exitCode=1;});
