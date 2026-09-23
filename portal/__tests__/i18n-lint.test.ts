import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";
import thLocale from "@/locale/th.json";
import enLocale from "@/locale/en.json";

function getFilesRecursively(dir: string, extensions: string[]): string[] {
  let results: string[] = [];
  if (!fs.existsSync(dir)) return results;

  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat && stat.isDirectory()) {
      results = results.concat(getFilesRecursively(filePath, extensions));
    } else {
      if (extensions.some((ext) => file.endsWith(ext))) {
        results.push(filePath);
      }
    }
  }
  return results;
}

describe("i18n Quality and Lint Enforcement", () => {
  it("enforces 100% key parity between Thai and English locale files", () => {
    const thKeys = Object.keys(thLocale).sort();
    const enKeys = Object.keys(enLocale).sort();

    const missingInEn = thKeys.filter((k) => !enKeys.includes(k));
    const missingInTh = enKeys.filter((k) => !thKeys.includes(k));

    expect(
      missingInEn,
      `Keys present in th.json but missing in en.json: ${missingInEn.join(", ")}`
    ).toEqual([]);

    expect(
      missingInTh,
      `Keys present in en.json but missing in th.json: ${missingInTh.join(", ")}`
    ).toEqual([]);

    expect(thKeys.length).toBeGreaterThan(0);
    expect(thKeys).toEqual(enKeys);
  });

  it("ensures zero raw Thai characters exist in portal/app and portal/components outside locale files", () => {
    const rootDir = path.resolve(__dirname, "..");
    const searchDirs = [
      path.join(rootDir, "app"),
      path.join(rootDir, "components"),
      path.join(rootDir, "lib"),
    ];

    const sourceFiles: string[] = [];
    searchDirs.forEach((dir) => {
      sourceFiles.push(...getFilesRecursively(dir, [".ts", ".tsx", ".js", ".jsx"]));
    });

    const thaiRegex = /[\u0E00-\u0E7F]/;
    const violations: { file: string; line: number; content: string }[] = [];

    sourceFiles.forEach((file) => {
      const content = fs.readFileSync(file, "utf-8");
      const lines = content.split("\n");
      lines.forEach((line, index) => {
        if (thaiRegex.test(line)) {
          violations.push({
            file: path.relative(rootDir, file),
            line: index + 1,
            content: line.trim(),
          });
        }
      });
    });

    expect(
      violations,
      `Found hardcoded Thai strings outside locale files:\n${violations
        .map((v) => `  ${v.file}:${v.line} -> ${v.content}`)
        .join("\n")}`
    ).toEqual([]);
  });

  it("ensures no hardcoded common English UI literals exist directly in JSX nodes", () => {
    const rootDir = path.resolve(__dirname, "..");
    const searchDirs = [
      path.join(rootDir, "app"),
      path.join(rootDir, "components"),
    ];

    const sourceFiles: string[] = [];
    searchDirs.forEach((dir) => {
      sourceFiles.push(...getFilesRecursively(dir, [".tsx"]));
    });

    // Check for raw English UI strings inside JSX tags: >Word<
    // Examples of forbidden direct text: >Login<, >Logout<, >Dashboard<, >Orders<, >Inventory<, >Approve<, >Reject<, >Status<, etc.
    const forbiddenDirectTexts = [
      ">Login<",
      ">Logout<",
      ">Orders<",
      ">Inventory<",
      ">Approve<",
      ">Reject<",
      ">Status<",
      ">Details<",
      ">Confirm<",
      ">Cancel<",
      ">Loading<",
      ">Error<",
      ">Retry<",
    ];

    const violations: { file: string; line: number; match: string }[] = [];

    sourceFiles.forEach((file) => {
      const content = fs.readFileSync(file, "utf-8");
      const lines = content.split("\n");
      lines.forEach((line, index) => {
        forbiddenDirectTexts.forEach((term) => {
          if (line.includes(term)) {
            violations.push({
              file: path.relative(rootDir, file),
              line: index + 1,
              match: term,
            });
          }
        });
      });
    });

    expect(
      violations,
      `Found hardcoded direct English UI text in JSX:\n${violations
        .map((v) => `  ${v.file}:${v.line} -> ${v.match}`)
        .join("\n")}`
    ).toEqual([]);
  });
});
