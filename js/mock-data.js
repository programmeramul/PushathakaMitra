// PustakaMitra AI — mock data. Clearly-labelled fixture data for UI development.
// All books, ratings, availability and library holdings are FICTIONAL placeholders.
// Do not ship as real Bengaluru library data. Replace via the service layer (js/services/api.js).

export const GENRES = [
  { id: "horror", en: "Horror", kn: "ಭಯಕಥೆ" },
  { id: "supernatural", en: "Supernatural", kn: "ಅಲೌಕಿಕ" },
  { id: "spirituality", en: "Spirituality", kn: "ಆಧ್ಯಾತ್ಮ" },
  { id: "mystery", en: "Mystery", kn: "ಮಿಸ್ಟರಿ" },
  { id: "fantasy", en: "Fantasy", kn: "ಫ್ಯಾಂಟಸಿ" },
  { id: "technology", en: "Technology", kn: "ತಂತ್ರಜ್ಞಾನ" },
  { id: "kannada", en: "Kannada Literature", kn: "ಕನ್ನಡ ಸಾಹಿತ್ಯ" },
];

// Books are mock fixtures with generated colour covers (no external images).
export const BOOKS = [
  { id: "b1", title: "Kagara Shikhāre", titleEn: "At the Misty Peak", author: "M. Anandarao", genres: ["kannada", "spirituality"], language: "Kannada", year: 1998, rating: 4.6, appReason: "You follow Kannada Literature and Spirituality — this classic blends a trek narrative with quiet philosophical reflections.", libCount: "[MOCK] in 4 demo libraries" },
  { id: "b2", title: "The Cipher in Hennur", author: "R. Sushmita", genres: ["mystery", "supernatural"], language: "English", year: 2021, rating: 4.3, appReason: "Sampled from your Mystery interest; a Bengaluru-set locked-room puzzle with a supernatural twist.", libCount: "[MOCK] in 6 demo libraries" },
  { id: "b3", title: "Mooru Ātmas", titleEn: "Three Souls of Karkala", author: "Bhavana Rao", genres: ["horror", "supernatural"], language: "Bilingual", year: 2020, rating: 4.5, appReason: "Your Horror and Supernatural picks drove this folk-horror rooted in coastal Karnataka legend.", libCount: "[MOCK] in 2 demo libraries" },
  { id: "b4", title: "Compile & Peace", author: "Vikram Joshi", genres: ["technology", "spirituality"], language: "English", year: 2023, rating: 4.0, appReason: "For the technology reader in you: essays on calm engineering practice — matched to your goal of mindful focus.", libCount: "[MOCK] in 3 demo libraries" },
  { id: "b5", title: "ಇಳಿಸೂರು ತಂಗಾಳಿ", titleEn: "Cold Winds of Ilisuru", author: "Sharadamma K.", genres: ["kannada", "mystery"], language: "Kannada", year: 1987, rating: 4.4, appReason: "A Kannada classic whodunit — pairs naturally with the mystery titles you finished last month.", libCount: "[MOCK] in 5 demo libraries" },
  { id: "b6", title: "The Ember Cartographer", titleEn: null, author: "Neela Subramanian", genres: ["fantasy", "technology"], language: "English", year: 2022, rating: 4.2, appReason: "Because you rated two graphic-novel fantasies highly: an engineer-mage maps a burning city.", libCount: "[MOCK] in 2 demo libraries" },
  { id: "b7", title: "Lamp in the Gulmohar", author: "F. D'Souza", genres: ["supernatural", "spirituality"], language: "English", year: 2019, rating: 4.1, appReason: "Matches your Supernatural interest with a gentler, devotional tone.", libCount: "[MOCK] in 1 demo library" },
  { id: "b8", title: "ಬೆಂಗಳೂರು ರಹಸ್ಯ", titleEn: "The Bengaluru Enigma", author: "Anitha Reddy", genres: ["mystery", "kannada"], language: "Bilingual", year: 2024, rating: 4.5, appReason: "Your followed genre Mystery + Kannada Literature; city trail mystery with parallel Kannada text.", libCount: "[MOCK] in 7 demo libraries" },
  { id: "b9", title: "Quantum Chinna Setty", author: "Girish Pai", genres: ["fantasy", "technology", "kannada"], language: "Kannada", year: 2023, rating: 3.9, appReason: "A speculative business-technologist saga originally serialised in Kannada — new for your shelf.", libCount: "[MOCK] in 3 demo libraries" },
];

// Bengaluru libraries: MOCK fixtures only. Availability is invented ("Clear: do not
// publish real holdings"). Branch names are generic, not real catalogues.
export const LIBRARIES = [
  { id: "l1", branch: "[MOCK] Indiranagar Reading Room", address: "12 Church Rd, Indiranagar, Bengaluru", catalogue: "https://example.org/catalogue/indiranagar", holds: { b1: "available", b2: "checked-out", b5: "available", b8: "available" } },
  { id: "l2", branch: "[MOCK] Basavanagudi Public Library demo", address: "3 Bull Temple Rd, Basavanagudi, Bengaluru", catalogue: "https://example.org/catalogue/basavanagudi", holds: { b1: "available", b3: "checked-out", b5: "waitlist", b8: "available" } },
  { id: "l3", branch: "[MOCK] Jayanagar Book House (sample)", address: "41 11th Main, 4th Block, Jayanagar, Bengaluru", catalogue: "https://example.org/catalogue/jayanagar", holds: { b2: "available", b4: "available", b6: "waitlist", b8: "checked-out" } },
  { id: "l4", branch: "[MOCK] Malleshwaram Wodeyar Library", address: "8 Sampige Rd, Malleshwaram, Bengaluru", catalogue: "https://example.org/catalogue/malleshwaram", holds: { b1: "waitlist", b3: "available", b5: "available", b7: "checked-out" } },
  { id: "l5", branch: "[MOCK] Whitefield Tech Readers' Nook", address: "2 ITPL Main Rd, Whitefield, Bengaluru", catalogue: "https://example.org/catalogue/whitefield", holds: { b4: "available", b6: "available", b9: "checked-out", b2: "waitlist" } },
];

export const AVAIL_LABEL = {
  available: "✔ Available",
  "checked-out": "✖ Checked out",
  waitlist: "◔ Waitlist",
};
