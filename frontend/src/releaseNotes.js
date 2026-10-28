/* Novedades que se muestran en una ventana al entrar, UNA vez por usuario.

   Cómo publicar una actualización: agrega una entrada NUEVA al principio de RELEASES con un
   `id` distinto (la fecha, ej. "2026-11-15"). Solo se muestra la más reciente: un usuario que
   estuvo tiempo sin entrar ve únicamente la última, nunca se le acumulan. Si una actualización
   no tiene nada que contarle a los usuarios, no agregues entrada.

   Textos cortos y en el idioma de los usuarios (qué pueden hacer ahora), no técnicos. */
export const RELEASES = [
  {
    // Sale el mismo día que la anterior: repite sus puntos para quien todavía no la vio.
    id: "2026-10-28.3",
    date: "28 de octubre de 2026",
    title: "Rehacer pedidos dañados, Rendimiento y Excel",
    items: [
      {
        icon: "🔁",
        title: "Rehacer un pedido dañado",
        text: "Al cancelar un pedido porque la pieza salió dañada, Zola te pregunta si quieres rehacerlo: se crea uno igual que pasa directo a En producción.",
      },
      {
        icon: "📈",
        title: "Rendimiento por cuenta",
        text: "Simple_Solutions3D tiene un módulo nuevo: Diego, Sntg y la Empresa por separado y todas juntas, mes a mes.",
      },
      {
        icon: "📊",
        title: "Ventas y Reparto en Excel",
        text: "En Ventas y en Reparto (beta), «Descargar Excel» baja la información ordenada; el del Reparto explica cada fórmula.",
      },
    ],
  },
  {
    // Sale el mismo día que la anterior: repite sus puntos para quien todavía no la vio.
    id: "2026-10-28.2",
    date: "28 de octubre de 2026",
    title: "Rendimiento por cuenta y Excel de ventas y Reparto",
    items: [
      {
        icon: "📈",
        title: "Rendimiento por cuenta",
        text: "Simple_Solutions3D tiene un módulo nuevo: Diego, Sntg y la Empresa por separado y todas juntas, mes a mes. Los ingresos van a quien registró la venta y cada costo a quien puso el recurso.",
      },
      {
        icon: "📊",
        title: "Ventas en Excel",
        text: "En Ventas, «Descargar Excel» baja todas las ventas con los filtros y el orden que elegiste, con el costo desglosado y de quién es cada costo.",
      },
      {
        icon: "🧾",
        title: "Reparto explicado paso a paso",
        text: "En Reparto (beta), el Excel trae cada fórmula, de dónde sale cada monto y una cuadratura. Es una guía: revísenlo entre todos antes de repartir.",
      },
    ],
  },
  {
    id: "2026-10-28",
    date: "28 de octubre de 2026",
    title: "Descarga tus ventas y el Reparto en Excel",
    items: [
      {
        icon: "📊",
        title: "Ventas en Excel",
        text: "En Ventas, «Descargar Excel» baja todas las ventas con los filtros y el orden que elegiste, con el costo desglosado y de quién es cada costo.",
      },
      {
        icon: "🧾",
        title: "Reparto explicado paso a paso",
        text: "En Reparto (beta), el Excel trae cada fórmula, de dónde sale cada monto y una cuadratura. Es una guía: revísenlo entre todos antes de repartir.",
      },
    ],
  },
  {
    id: "2026-10-26",
    date: "26 de octubre de 2026",
    title: "Fuente de venta y hoja de ventas más cómoda",
    items: [
      {
        icon: "📣",
        title: "¿De dónde llegó la venta?",
        text: "Al registrar una venta eliges Instagram, Facebook o Personal. En el Dashboard y el Historial ves qué canal vende más.",
      },
      {
        icon: "📋",
        title: "100 ventas por página",
        text: "La hoja de ventas ahora muestra hasta 100 ventas antes de pasar de página.",
      },
      {
        icon: "↕️",
        title: "Ordena como quieras",
        text: "Toca Precio, Ganancia, Costo, Margen, Pedido o Cliente para ordenar de mayor a menor (otro toque invierte), o usa \"Ordenar por\".",
      },
      {
        icon: "🤖",
        title: "Discord no se salta pedidos",
        text: "Si se registran muchos pedidos seguidos, el bot los publica todos, uno tras otro.",
      },
    ],
  },
  {
    id: "2026-10-22",
    date: "22 de octubre de 2026",
    title: "Conexión más estable",
    items: [
      {
        icon: "🔐",
        title: "Tu sesión ya no se corta",
        text: "Se acabaron los avisos de \"Not Found\" al usar la Calculadora o Ventas después de un rato, y la sesión se mantiene al recargar, también en iPhone.",
      },
      {
        icon: "💬",
        title: "Mensajes claros al entrar",
        text: "Si el servidor está despertando o no hay conexión, el login lo dice en vez de marcar la contraseña como incorrecta. El usuario se acepta con o sin mayúsculas.",
      },
      {
        icon: "🔗",
        title: "Los enlaces abren directo",
        text: "Recargar una sección o abrir un enlace del aviso de Discord ya no muestra una página de error.",
      },
    ],
  },
  {
    // Sale el mismo día que la anterior: repite sus puntos para quien todavía no la vio.
    id: "2026-10-20.3",
    date: "20 de octubre de 2026",
    title: "Colores de filamento confiables y gráficos con vida",
    items: [
      {
        icon: "🎨",
        title: "El color del carrete siempre se ve",
        text: "La foto del carrete se pinta del tono elegido en todos los navegadores, también en el celular. Si la foto tardara en cargar, ves un círculo del color en vez de un espacio vacío.",
      },
      {
        icon: "💾",
        title: "El tono queda como lo dejaste",
        text: "Editar un filamento ya no le cambia el color a gris por error.",
      },
      {
        icon: "🧮",
        title: "Calculadora animada",
        text: "Al calcular, el desglose de costos se dibuja por partes y los escenarios muestran en barras cuánto es costo y cuánto ganancia.",
      },
      {
        icon: "📈",
        title: "Historial y Dashboard",
        text: "Los gráficos crecen y se dibujan al aparecer, y cada mes del Historial trae su mini tendencia.",
      },
    ],
  },
  {
    // Sale el mismo día que la anterior: repite sus puntos para quien todavía no la vio.
    id: "2026-10-20.2",
    date: "20 de octubre de 2026",
    title: "Gráficos con vida",
    items: [
      {
        icon: "🧮",
        title: "Calculadora animada",
        text: "Al calcular, el desglose de costos se dibuja por partes y los escenarios muestran en barras cuánto es costo y cuánto ganancia. El precio manual se mueve mientras lo escribes.",
      },
      {
        icon: "📈",
        title: "Historial y Dashboard",
        text: "Los gráficos crecen y se dibujan al aparecer, y cada mes del Historial trae su mini tendencia. Toca una parte de la dona para ver su detalle.",
      },
      {
        icon: "🌈",
        title: "Dashboard renovado",
        text: "Arriba ves tu ganancia con su tendencia, un gráfico de ganancia mensual y qué impresoras están Ocupadas o Libres.",
      },
      {
        icon: "📱",
        title: "Barra inferior en el celular",
        text: "Inicio, Ventas y Agenda a mano del pulgar; el botón + registra una venta nueva y \"Más\" abre el menú completo.",
      },
      {
        icon: "✨",
        title: "Tú decides cuánto se mueve",
        text: "El botón con estrellitas de la barra superior reduce las animaciones si prefieres una app más quieta.",
      },
    ],
  },
  {
    id: "2026-10-20",
    date: "20 de octubre de 2026",
    title: "Zola con nuevo movimiento",
    items: [
      {
        icon: "🌈",
        title: "Dashboard renovado",
        text: "Arriba ves tu ganancia con su tendencia de los últimos meses, un gráfico de ganancia mensual y qué impresoras están Ocupadas (con un pedido En producción) o Libres.",
      },
      {
        icon: "📱",
        title: "Barra inferior en el celular",
        text: "Inicio, Ventas y Agenda quedan a mano del pulgar, y el botón + registra una venta nueva. \"Más\" abre el menú completo.",
      },
      {
        icon: "✅",
        title: "Confirmación al guardar",
        text: "Al registrar una venta o cambiar un estado aparece un aviso abajo. En Ventas puedes filtrar rápido entre Todas, Abiertas y Entregadas.",
      },
      {
        icon: "✨",
        title: "Tú decides cuánto se mueve",
        text: "El botón con estrellitas de la barra superior reduce las animaciones si prefieres una app más quieta.",
      },
    ],
  },
  {
    id: "2026-10-13",
    date: "13 de octubre de 2026",
    title: "Más fluida y sin parpadeos",
    items: [
      {
        icon: "⚡",
        title: "Sin parpadeos al actualizar",
        text: "Al cambiar un estado o guardar, la información ya no desaparece: se actualiza en su lugar. Una barra fina arriba indica que está trabajando.",
      },
      {
        icon: "✨",
        title: "Animaciones nuevas",
        text: "Las páginas, tarjetas, ventanas y el menú se mueven con más fluidez, y los números del Dashboard cuentan hasta su valor.",
      },
      {
        icon: "🔆",
        title: "Se ve qué cambió",
        text: "En Ventas, el pedido que acabas de modificar se ilumina un instante.",
      },
    ],
  },
  {
    // Sale el mismo día que la anterior: repite sus puntos para quien todavía no la vio.
    id: "2026-10-05.2",
    date: "5 de octubre de 2026",
    title: "Nombres de color propios y materiales de varios socios",
    items: [
      {
        icon: "🎨",
        title: "Tú pones el nombre del color",
        text: "Al agregar un filamento escribe el nombre que quieras (Burdeo, Verde transparente...). La paleta y el selector RGB solo eligen el tono.",
      },
      {
        icon: "🧩",
        title: "Materiales de varios socios",
        text: "Simple_Solutions3D puede vender usando impresora, filamento e insumos de Diego y Sntg a la vez. Cada costo queda a cuenta de su dueño.",
      },
      {
        icon: "⚠️",
        title: "Siempre con aviso",
        text: "Al mezclar dueños verás un aviso y una confirmación al guardar, y la venta queda marcada como «Materiales mixtos».",
      },
      {
        icon: "🎁",
        title: "Regalos fuera del reparto",
        text: "Un regalo ya no reparte sus costos entre todos: lo absorbe quien regaló.",
      },
    ],
  },
  {
    id: "2026-10-05",
    date: "5 de octubre de 2026",
    title: "La Empresa combina materiales de los socios",
    items: [
      {
        icon: "🧩",
        title: "Materiales de varios socios",
        text: "Simple_Solutions3D puede vender usando la impresora, el filamento y los insumos de Diego y Sntg a la vez (y los propios).",
      },
      {
        icon: "⚖️",
        title: "Cada costo a su dueño",
        text: "Se descuenta del inventario de cada uno y la máquina, el material y los insumos quedan a cuenta de quien los puso. La ganancia se reparte como siempre.",
      },
      {
        icon: "⚠️",
        title: "Siempre con aviso",
        text: "Al mezclar dueños verás un aviso y una confirmación al guardar, y la venta queda marcada como «Materiales mixtos».",
      },
      {
        icon: "🎁",
        title: "Regalos fuera del reparto",
        text: "Un regalo ya no reparte sus costos entre todos: lo absorbe quien regaló.",
      },
    ],
  },
  {
    // Sale el mismo día que la anterior: repite sus puntos para quien todavía no la vio.
    id: "2026-10-02.2",
    date: "2 de octubre de 2026",
    title: "Minutos de impresión, Cuenta Empresa y más",
    items: [
      {
        icon: "⏱️",
        title: "Horas y minutos",
        text: "El tiempo de impresión ahora se ingresa en horas y minutos: ya no hay que convertir los minutos a mano.",
      },
      {
        icon: "🎯",
        title: "Riesgo de fallo",
        text: "Al cotizar o vender eliges riesgo bajo, medio o alto (10/15/20 %). Se cobra aparte del margen. Los insumos ahora sí llevan margen.",
      },
      {
        icon: "🏢",
        title: "Cuenta Empresa",
        text: "Olzer ahora es Simple_Solutions3D (misma contraseña), con inventario propio. Cada venta muestra cuánto pone cada uno.",
      },
      {
        icon: "🛵",
        title: "Delivery",
        text: "«Envío» ahora se llama Delivery. Indica quién lo lleva: ese monto se le devuelve a esa persona.",
      },
      {
        icon: "📊",
        title: "Nuevo en beta: Reparto y Mi inversión",
        text: "Una guía del reparto del mes y de cuánto lleva recuperado cada socio. Búscalas en el menú.",
      },
    ],
  },
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
