/* Fechas del Calendario (siempre en hora local). Las comparte la pantalla del Calendario y
   la precarga en segundo plano, para pedir exactamente el mismo rango.

   Todas las fechas se fijan al MEDIODÍA: en Chile el cambio de horario de verano ocurre
   a medianoche (ese día las 00:00 no existen), y con fechas a medianoche un día podía
   correrse una hora y caerse del calendario. */
export const CALENDAR_VIEWS = [
  { key: "month", label: "Mes" },
  { key: "week", label: "Semana" },
  { key: "day", label: "Día" },
];
export const CALENDAR_VIEW_KEY = "zola:calendar:view";

export function readSavedCalendarView() {
  try {
    const v = localStorage.getItem(CALENDAR_VIEW_KEY);
    return CALENDAR_VIEWS.some((x) => x.key === v) ? v : "month";
  } catch {
    return "month";
  }
}

export function atNoon(y, m, d) {
  return new Date(y, m, d, 12);
}
export function parseISO(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return atNoon(y, m - 1, d);
}
export function addDays(date, n) {
  return atNoon(date.getFullYear(), date.getMonth(), date.getDate() + n);
}
export function startOfWeek(date) {
  // Semana de lunes a domingo.
  return addDays(date, -((date.getDay() + 6) % 7));
}

export function calendarRange(view, cursor) {
  const c = cursor;
  if (view === "month") {
    const first = startOfWeek(atNoon(c.getFullYear(), c.getMonth(), 1));
    return { from: first, to: addDays(first, 41), count: 42 };
  }
  if (view === "week") {
    const from = startOfWeek(c);
    return { from, to: addDays(from, 6), count: 7 };
  }
  return { from: c, to: c, count: 1 };
}
