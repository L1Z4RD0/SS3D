<script setup>
defineProps({
  color: { type: String, required: true },
  size: { type: [Number, String], default: 40 },
});
</script>

<template>
  <div
    class="spool-icon"
    :style="{ width: typeof size === 'number' ? size + 'px' : size, height: typeof size === 'number' ? size + 'px' : size }"
  >
    <img class="spool-base" src="/img/FilamentoIMG.png" alt="" />
    <div class="spool-tint" :style="{ backgroundColor: color }"></div>
  </div>
</template>

<style scoped>
/* Colorizes a real spool photo (frontend/public/img/FilamentoIMG.png -- white filament,
   black plastic bobbin, transparent background) to any filament color without touching
   the source image: a copy of the same image is used as a luminance mask on a solid-color
   layer, so the color only shows over the bright filament coil (mask-mode: luminance maps
   white -> fully visible, black -> fully hidden). mix-blend-mode: multiply then blends that
   color with the base photo underneath, so the coil's own shading/highlights survive as
   tinted light/dark variations instead of a flat color fill. The black bobbin is masked out
   of the color layer entirely, so it keeps showing through from the untouched base image.
   Requires being served over http(s) -- masked images render blank under file://. */
.spool-icon {
  position: relative;
  flex-shrink: 0;
}

.spool-base {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.spool-tint {
  position: absolute;
  inset: 0;
  mix-blend-mode: multiply;
  -webkit-mask-image: url("/img/FilamentoIMG.png");
  -webkit-mask-mode: luminance;
  -webkit-mask-size: contain;
  -webkit-mask-repeat: no-repeat;
  -webkit-mask-position: center;
  mask-image: url("/img/FilamentoIMG.png");
  mask-mode: luminance;
  mask-size: contain;
  mask-repeat: no-repeat;
  mask-position: center;
}
</style>
