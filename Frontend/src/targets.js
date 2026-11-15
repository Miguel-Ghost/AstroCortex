export const TARGETS = [
  {
    target_id: "barnard",
    name: "Barnard's Star",
    short: "Barnard",
    default_detector: 2,
    aliases: ["barnard", "barnards star", "gj 699"],
  },
  {
    target_id: "epsindib",
    name: "Epsilon Indi B",
    short: "Eps Indi B",
    default_detector: 5,
    aliases: ["eps indi b", "epsilon indi b", "eps ind b"],
  },
  {
    target_id: "wise0855",
    name: "WISE 0855-0714",
    short: "WISE 0855",
    default_detector: 5,
    aliases: ["wise0855", "wise 0855", "wise j085510.83-071442.5"],
  },
  {
    target_id: "rwaur",
    name: "RW Aurigae",
    short: "RW Aur",
    default_detector: 3,
    aliases: ["rw aur"],
  },
  {
    target_id: "rdra",
    name: "R Draconis",
    short: "R Dra",
    default_detector: 3,
    aliases: ["r dra"],
  },
];
export const findTargetByName = (q) =>
  TARGETS.find((t) =>
    [t.target_id, t.name, ...t.aliases].some(
      (a) => a.toLowerCase() === q.trim().toLowerCase(),
    ),
  );
