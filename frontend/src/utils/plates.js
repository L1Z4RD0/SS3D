// Planchas adicionales -> formato de la API.
export function platesPayload(plates) {
  return plates.map((p) => ({
    name: (p.name || "").trim(),
    printer_id: p.printer_id,
    print_hours: Number(p.print_hours) || 0,
    filaments: p.filaments.map((r) => ({ filament_id: r.filament_id, grams_used: Number(r.grams_used) })),
  }));
}

// Mensaje de error para la primera plancha incompleta, o "" si están todas bien.
export function platesError(plates) {
  for (const [i, p] of plates.entries()) {
    const label = p.name?.trim() || `la plancha ${i + 2}`;
    if (!p.name?.trim()) return `Ponle un nombre a la plancha ${i + 2}.`;
    if (!p.printer_id) return `Elige la impresora de ${label}.`;
    if (!(Number(p.print_hours) >= 0)) return `Las horas de ${label} no pueden ser negativas.`;
  }
  return "";
}
