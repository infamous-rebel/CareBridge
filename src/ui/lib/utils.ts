import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Strip internal IDs, care_recipient refs, and raw ISO timestamps from rationale text. */
export function cleanRationale(text: string): string {
  return text
    .replace(/\s*\(id=[^)]+\)/gi, "")
    .replace(/\s*for care_recipient=[^\s]+/gi, "")
    .replace(/\s*at \d{4}-\d{2}-\d{2}T[\d:.]+Z?/gi, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}
