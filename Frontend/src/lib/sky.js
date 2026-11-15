let primary, compatible;
function canvasRenderer() {
  if (!compatible)
    compatible = (async () => {
      const { default: $ } = await import("jquery");
      window.$ = window.jQuery = $;
      if (!document.querySelector("link[data-aladin-canvas]")) {
        const css = document.createElement("link");
        css.rel = "stylesheet";
        css.href = "/vendor/aladin-v2.min.css";
        css.dataset.aladinCanvas = "true";
        document.head.append(css);
      }
      await new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "/vendor/aladin-v2.min.js";
        script.onload = resolve;
        script.onerror = () =>
          reject(Error("The compatible sky renderer could not be loaded."));
        document.head.append(script);
      });
      if (!window.A?.aladin)
        throw Error("The compatible sky renderer is unavailable.");
      return { A: window.A, renderer: "canvas" };
    })().catch((e) => {
      compatible = null;
      throw e;
    });
  return compatible;
}
export async function loadSky() {
  // Use the same Aladin v3 release as the supplied HTML, served with the app.
  // Aladin v2 preserves the sky on browsers without WebGL2; never invent survey pixels.
  if (!primary)
    primary = import("aladin-lite").then(async (module) => {
      await module.default.init;
      return { A: module.default, renderer: "webgl2" };
    });
  try {
    return await primary;
  } catch {
    return canvasRenderer();
  }
}
export const ALLWISE_URL =
  "https://irsa.ipac.caltech.edu/data/hips/CDS/AllWISE/RGB-W4-W2-W1";
export const TWOMASS_URL =
  "https://irsa.ipac.caltech.edu/data/hips/CDS/2MASS/Color";
export function initialSurvey(A, renderer) {
  if (renderer !== "canvas") return ALLWISE_URL;
  const survey = A.imageLayer("allwise", "AllWISE", ALLWISE_URL, {
    imgFormat: "jpg",
  });
  survey.maxOrder = 8;
  // Pinned upstream v2 adapter: retain the original, unmodified HiPS Allsky atlas
  // locally, while higher-resolution tiles still load from IRSA when online.
  const original = survey.init;
  survey.init = function (view, done) {
    let completed = false;
    const ready = () => {
      if (!completed) {
        completed = true;
        done?.();
      }
    };
    original.call(this, view, ready);
    const image = new Image();
    image.onload = () => {
      this.allskyTexture = image;
      this.allskyTextureSize = image.width / 27;
      this.useCors = true;
      ready();
      view.requestRedraw();
    };
    image.src = "/static/sky/allwise/Norder3/Allsky.jpg";
  };
  return survey;
}
export async function selectSurvey(A, renderer, url, name) {
  if (renderer !== "canvas") return url;
  if (url === ALLWISE_URL) return initialSurvey(A, renderer);
  if (!url.startsWith("https://"))
    throw Error(
      "This survey requires WebGL2. You can keep exploring AllWISE or 2MASS.",
    );
  const r = await fetch(url + "/properties", {
    signal: AbortSignal.timeout(12000),
  });
  if (!r.ok) throw Error("Survey unavailable.");
  const props = Object.fromEntries(
    (await r.text())
      .split(/\r?\n/)
      .filter((l) => l.includes("="))
      .map((l) => {
        const i = l.indexOf("=");
        return [l.slice(0, i).trim(), l.slice(i + 1).trim()];
      }),
  );
  const survey = A.imageLayer(url, name, url, {
    imgFormat: props.hips_tile_format?.includes("jpeg") ? "jpg" : "png",
  });
  survey.maxOrder = Number(props.hips_order);
  return survey;
}
