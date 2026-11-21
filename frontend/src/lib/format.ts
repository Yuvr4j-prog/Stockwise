const moneyFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

const integerFormatter = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 0,
});

export function money(value: number | string | null | undefined): string {
  const number = Number(value ?? 0);
  return moneyFormatter.format(Number.isFinite(number) ? number : 0);
}

export function quantity(value: number | string | null | undefined): string {
  const number = Number(value ?? 0);
  return integerFormatter.format(Number.isFinite(number) ? number : 0);
}

export function decimal(value: number | string | null | undefined): string {
  const number = Number(value ?? 0);
  return new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    .format(Number.isFinite(number) ? number : 0);
}

export function shortDate(value: string): string {
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" })
    .format(new Date(value));
}

export function currentIsoWeek(): { year: number; week: number } {
  const date = new Date();
  const utc = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  utc.setUTCDate(utc.getUTCDate() + 4 - (utc.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(utc.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((utc.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return { year: utc.getUTCFullYear(), week };
}
