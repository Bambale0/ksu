/** Check explicitly advertised file formats before spending time on an upload.
 * Generic media wildcards retain server-side probing (for example audio-only MP4).
 * This is a UX guard; the server still verifies the actual file contents.
 */
export function assertUploadFileType(file: File, accept?: string): void {
  const tokens = String(accept || "").toLowerCase().split(",").map(token => token.trim()).filter(Boolean);
  const extensions = tokens.filter(token => /^\.[a-z0-9]+$/.test(token));
  if (!extensions.length) return;
  const name = file.name.toLowerCase();
  const type = file.type.toLowerCase();
  const matches = tokens.some(token => token.startsWith(".")
    ? name.endsWith(token)
    : token.endsWith("/*") ? type.startsWith(token.slice(0, -1)) : type === token);
  if (matches) return;
  const formats = extensions.map(token => token.slice(1).toUpperCase()).join(", ");
  throw new Error(`Поддерживаемые форматы: ${formats}. Выберите другой файл.`);
}
