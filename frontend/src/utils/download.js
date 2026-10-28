/* Descarga de archivos generados por el servidor (Excel): se piden con la sesión del
   usuario (axios lleva el token) y se guardan con el nombre que manda el servidor. */
export function saveBlobResponse(response, fallbackName) {
  const disposition = response.headers?.["content-disposition"] || "";
  const name = /filename="?([^";]+)"?/i.exec(disposition)?.[1] || fallbackName;
  const url = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Se libera después: algunos navegadores necesitan el enlace vivo un instante.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
