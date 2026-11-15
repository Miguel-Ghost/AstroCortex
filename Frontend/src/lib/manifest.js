export const frameFor = (m, i, d) =>
  m?.epochs[i]?.frames.find((f) => f.detector === d);
export const availableEpochs = (m, d, grid = false) =>
  m?.epochs.flatMap((e, i) =>
    (grid ? e.frames.length : e.frames.some((f) => f.detector === d))
      ? [i]
      : [],
  ) || [];
export const positionFor = (source, epoch) =>
  source?.positions?.[epoch?.epoch_id] || epoch?.expected_position || null;
export function validateManifest(m) {
  if (
    !m ||
    !Number.isInteger(m.nx) ||
    m.nx < 1 ||
    !Number.isInteger(m.ny) ||
    m.ny < 1 ||
    !Array.isArray(m.epochs) ||
    !m.epochs.length ||
    !Array.isArray(m.detectors) ||
    !Number.isFinite(m.center?.ra) ||
    !Number.isFinite(m.center?.dec)
  )
    throw Error("Invalid field manifest");
  return m;
}
