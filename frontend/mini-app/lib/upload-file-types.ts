/** Browser format filtering is advisory; the server still probes actual bytes. */
type FileType = Pick<File, "name" | "type">;

function formatTokens(accept?: string): string[] {
  return String(accept || "").toLowerCase().split(",").map(token => token.trim()).filter(Boolean);
}

export function uploadFileTypeMatches(file: FileType, accept?: string): boolean {
  const tokens = formatTokens(accept);
  // Preserve generic media probing, including audio-only MP4 containers.
  if (!tokens.some(token => /^\.[a-z0-9]+$/.test(token))) return true;
  const name = file.name.toLowerCase();
  const type = file.type.toLowerCase();
  return tokens.some(token => token.startsWith(".")
    ? name.endsWith(token)
    : token.endsWith("/*") ? type.startsWith(token.slice(0, -1)) : type === token);
}

export function assertUploadFileType(file: FileType, accept?: string): void {
  if (uploadFileTypeMatches(file, accept)) return;
  const formats = formatTokens(accept).filter(token => /^\.[a-z0-9]+$/.test(token))
    .map(token => token.slice(1).toUpperCase()).join(", ");
  throw new Error(`Поддерживаемые форматы: ${formats}. Выберите другой файл.`);
}
