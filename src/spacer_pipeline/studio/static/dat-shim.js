// Runs the vendored knitout-to-dat.js (a Node command-line script) without
// Node: its only file reads/writes are redirected to a string and a byte
// array, so the unmodified script works inside the Knit Studio window.
(function (root) {
  "use strict";

  function createDatConverter(source) {
    // Node strips a leading "#!" line; Function() does not accept it.
    const body = source.replace(/^#![^\n]*\n/, "");
    const script = new Function("require", "process", "Buffer", "console", body);

    return function knitoutToDat(knitoutText) {
      let bytes = null;
      const warnings = [];
      const fs = {
        readFileSync: () => knitoutText,
        writeFileSync: (_path, data) => { bytes = data; },
      };
      const note = (...args) => warnings.push(args.map(String).join(" "));
      const quietConsole = {
        log: () => {}, info: () => {}, warn: note, error: note,  // log/info are progress chatter
        assert: (ok, ...args) => { if (!ok) note("Assertion failed:", ...args); },
      };
      const require = (name) => {
        if (name === "fs") return fs;
        throw new Error("knitout-to-dat needs unsupported module " + name);
      };
      const process = { argv: ["node", "knitout-to-dat.js", "in.k", "out.dat"], exitCode: 0 };
      const Buffer = { from: (array) => array };
      script(require, process, Buffer, quietConsole);
      if (!bytes) throw new Error(warnings.join("\n") || "knitout-to-dat produced no output");
      return { bytes, warnings };
    };
  }

  root.createDatConverter = createDatConverter;
  if (typeof module !== "undefined") module.exports = { createDatConverter };
})(typeof globalThis !== "undefined" ? globalThis : this);
