import { parse } from "yaml";
export function validateMetric(text: string, runtime: string) {
  const errors: string[] = [];
  let value: any;
  try {
    value = parse(text, { uniqueKeys: true, maxAliasCount: 20 });
  } catch (e) {
    return { errors: [`Invalid YAML: ${(e as Error).message}`], value: null };
  }
  if (!value || typeof value !== "object" || Array.isArray(value))
    return { errors: ["Expected a YAML object"], value: null };
  const keys = [
    "version",
    "source",
    "comment",
    "filter",
    "joins",
    "fields",
    "dimensions",
    "measures",
  ];
  for (const k of Object.keys(value))
    if (!keys.includes(k))
      errors.push(
        `Unsupported native field: ${k}. UOL annotations must remain separate.`,
      );
  if (String(value.version) !== "1.1")
    errors.push("This editor supports native YAML 1.1 only.");
  for (const k of ["comment", "filter"])
    if (value[k] !== undefined && typeof value[k] !== "string")
      errors.push(`${k} must be a string`);
  if (!Number.isFinite(Number(runtime)) || Number(runtime) < 17.3)
    errors.push("Agent metadata requires Runtime 17.3+ and YAML 1.1.");
  if (typeof value.source !== "string" || !value.source.trim())
    errors.push("Source is required.");
  if (!Array.isArray(value.measures) || !value.measures.length)
    errors.push("At least one measure is required by this editor.");
  for (const group of ["fields", "dimensions", "measures"])
    if (value[group]) {
      if (!Array.isArray(value[group])) {
        errors.push(`${group} must be an array`);
        continue;
      }
      for (const f of value[group]) {
        if (!f || typeof f !== "object" || Array.isArray(f)) {
          errors.push(`${group}: invalid entry`);
          continue;
        }
        for (const k of Object.keys(f))
          if (
            ![
              "name",
              "expr",
              "display_name",
              "synonyms",
              "format",
              "comment",
            ].includes(k)
          )
            errors.push(`Unsupported ${group} field: ${k}`);
        if (
          typeof f.name !== "string" ||
          !f.name.trim() ||
          typeof f.expr !== "string" ||
          !f.expr.trim()
        )
          errors.push(`${group}: name and expression required`);
        for (const k of ["display_name", "comment"])
          if (f[k] !== undefined && typeof f[k] !== "string")
            errors.push(`${group}: ${k} must be a string`);
        if (
          f.format !== undefined &&
          (!f.format || typeof f.format !== "object" || Array.isArray(f.format))
        )
          errors.push("format must be an object");
        if (f.format && typeof f.format === "object") {
          if (
            ![
              "number",
              "currency",
              "percentage",
              "byte",
              "date",
              "date_time",
            ].includes(f.format.type)
          )
            errors.push("Unsupported formatting type.");
          const d = f.format.decimal_places;
          if (
            d &&
            (!["max", "exact", "all"].includes(d.type) ||
              (d.type !== "all" &&
                (!Number.isInteger(d.places) || d.places < 0 || d.places > 10)))
          )
            errors.push("Invalid decimal_places formatting.");
        }
        if (
          f.synonyms !== undefined &&
          (!Array.isArray(f.synonyms) ||
            f.synonyms.length > 10 ||
            f.synonyms.some(
              (x: any) => typeof x !== "string" || x.length > 255,
            ))
        )
          errors.push(
            "Synonyms must be up to 10 strings of at most 255 characters.",
          );
      }
    }
  if (value.joins) {
    if (!Array.isArray(value.joins)) errors.push("Joins must be an array");
    else
      for (const j of value.joins) {
        if (!j || typeof j !== "object" || Array.isArray(j)) {
          errors.push("Invalid join entry");
          continue;
        }
        if (!j.name || !j.source || !j.on)
          errors.push("Joins require name, source and on.");
        if (j.cardinality && Number(runtime) < 18.1)
          errors.push("Join cardinality requires Runtime 18.1+.");
        for (const k of Object.keys(j))
          if (!["name", "source", "on", "cardinality"].includes(k))
            errors.push(`Unsupported join field: ${k}`);
      }
  }
  return { errors, value };
}
