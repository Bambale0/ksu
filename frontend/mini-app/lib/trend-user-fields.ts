import type { TrendUserField } from "./types";

// Keep semantics aligned with app/services/trend_user_fields.py and the catalog corpus.
const NUMBER_FIELD_WORDS = new Set(["возраст","возраста","число","числа","чисел","цифра","цифры","цифр","цифру","цифре","цифрами","количество","количества","номер","номера","номеров","рост","роста","вес","веса","лет","год","года","годы","годов","свеча","свечи","свечей","свечах"]);
const DATE_FIELD_WORDS = new Set(["дата", "date", "birthday", "birthdate"]);
const TEXT_FIELD_START_WORDS = new Set(["текст","надпись","фраза","слоган","имя","фамилия","название","цвет","оттенок","палитра","caption","text","name","title","color","colour"]);
const EXAMPLE_WORDS = new Set(["пример", "например", "example"]);

export function inferTemplateFieldType(label: string): TrendUserField["type"] {
  let normalized = label.trim().toLowerCase();
  while (true) {
    const clean = normalized.replace(/\([^()]*\)/g, " ");
    if (clean === normalized) break;
    normalized = clean;
  }
  normalized = normalized.split("(", 1)[0].split(":", 1)[0];
  let words: string[] = normalized.match(/\p{L}+/gu) || [];
  const example = words.findIndex((word) => EXAMPLE_WORDS.has(word));
  if (example >= 0) words = words.slice(0, example);
  if (words.length && TEXT_FIELD_START_WORDS.has(words[0])) return "text";

  const semanticWords: string[] = [];
  for (let index = 0; index < words.length; index += 1) {
    if (words[index] === "время" && words[index + 1] === "года") index += 1;
    else semanticWords.push(words[index]);
  }
  if (
    semanticWords.some((word) => DATE_FIELD_WORDS.has(word)) ||
    semanticWords.some((word, index) => word === "день" && semanticWords[index + 1] === "рождения")
  ) return "date";
  return semanticWords.some((word) => NUMBER_FIELD_WORDS.has(word)) ? "number" : "text";
}
