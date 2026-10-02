/* Novedades que se muestran en una ventana al entrar, UNA vez por usuario.

   Cómo publicar una actualización: agrega una entrada NUEVA al principio de RELEASES con un
   `id` distinto (la fecha, ej. "2026-11-15"). Solo se muestra la más reciente: un usuario que
   estuvo tiempo sin entrar ve únicamente la última, nunca se le acumulan. Si una actualización
   no tiene nada que contarle a los usuarios, no agregues entrada.

   Textos cortos y en el idioma de los usuarios (qué pueden hacer ahora), no técnicos. */
export const RELEASES = [
  {
    id: "2026-10-02",
    date: "2 de octubre de 2026",
    title: "Cuenta Empresa, riesgo de fallo y Reparto",
    items: [
      {
        icon: "🎯",
        title: "Riesgo de fallo",
        text: "Al cotizar o vender eliges riesgo bajo, medio o alto (10/15/20 %). Se cobra aparte del margen. Los insumos ahora sí llevan margen.",
      },
      {
        icon: "🏢",
        title: "Cuenta Empresa",
        text: "Olzer ahora es Simple_Solutions3D (misma contraseña). Tiene inventario propio y puede vender con la impresora de un socio usando su filamento.",
      },
      {
        icon: "🛵",
        title: "Delivery",
        text: "«Envío» ahora se llama Delivery. Indica quién lo lleva: ese monto se le devuelve a esa persona.",
      },
      {
        icon: "🧾",
        title: "Costos por cuenta",
        text: "En el detalle de cada venta ves cuánto pone cada uno: máquina, material e insumos.",
      },
      {
        icon: "📊",
        title: "Nuevo en beta: Reparto y Mi inversión",
        text: "Una guía del reparto del mes y de cuánto lleva recuperado cada socio. Búscalas en el menú.",
      },
    ],
  },
];

export const LATEST_RELEASE = RELEASES[0] || null;
