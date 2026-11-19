import type { LanguageFinding, LanguageQualityReport, TextLineInfo } from '../types/cv';

export const COMMON_MISSPELLINGS: Record<string, string> = {
  recieved: 'received',
  recieve: 'receive',
  acheivement: 'achievement',
  achievment: 'achievement',
  acheivements: 'achievements',
  achievments: 'achievements',
  experiance: 'experience',
  experince: 'experience',
  managment: 'management',
  mangement: 'management',
  fianance: 'finance',
  finacial: 'financial',
  finanacial: 'financial',
  accouting: 'accounting',
  accountng: 'accounting',
  bussiness: 'business',
  buisness: 'business',
  responsibilites: 'responsibilities',
  responsiblities: 'responsibilities',
  responsiblity: 'responsibility',
  communiction: 'communication',
  communcation: 'communication',
  proficiant: 'proficient',
  proficency: 'proficiency',
  proficeincy: 'proficiency',
  excelent: 'excellent',
  excellant: 'excellent',
  knowledgable: 'knowledgeable',
  seperate: 'separate',
  occured: 'occurred',
  untill: 'until',
  wich: 'which',
  teh: 'the',
  adn: 'and',
  succesful: 'successful',
  sucessful: 'successful',
  collegue: 'colleague',
  refree: 'referee',
  refrees: 'referees',
  curriculam: 'curriculum',
  curiculum: 'curriculum',
  diplamo: 'diploma',
  certifcate: 'certificate',
  certficate: 'certificate',
  analysys: 'analysis',
  evalution: 'evaluation',
  custmer: 'customer',
  custommer: 'customer',
  documetation: 'documentation',
  documentaion: 'documentation',
  reconcilation: 'reconciliation',
  reconcilliation: 'reconciliation',
  complaince: 'compliance',
  complince: 'compliance',
  transacion: 'transaction',
  transcation: 'transaction',
  calender: 'calendar',
  independant: 'independent',
  maintenence: 'maintenance',
  supervison: 'supervision',
  microsft: 'Microsoft',
  powerpiont: 'PowerPoint',
  excell: 'Excel',
  languge: 'language',
  langauge: 'language',
  activites: 'activities',
  extraccuricular: 'extracurricular',
  voluntering: 'volunteering',
  graduted: 'graduated',
  univeristy: 'university',
  universtiy: 'university',
  instituton: 'institution',
  enviroment: 'environment',
  improvment: 'improvement',
  developement: 'development',
  organisaton: 'organisation',
  organizaton: 'organization',
  knowlege: 'knowledge',
  assitant: 'assistant',
  assistnt: 'assistant',
  managar: 'manager',
  execuitve: 'executive',
  internhsip: 'internship',
  intership: 'internship',
  treasuer: 'treasurer',
  secratary: 'secretary',
  presantations: 'presentations',
  presentaion: 'presentation',
  strenghts: 'strengths',
  strenght: 'strength',
  summery: 'summary',
  qualificaton: 'qualification',
  qualificatons: 'qualifications',
  refernces: 'references',
  accurancy: 'accuracy',
  acuracy: 'accuracy',
  efficent: 'efficient',
  effecient: 'efficient',
};

export const PROFESSIONAL_ACTION_VERBS = [
  'analyzed',
  'analysed',
  'assisted',
  'audited',
  'balanced',
  'built',
  'calculated',
  'collaborated',
  'compiled',
  'conducted',
  'coordinated',
  'created',
  'delivered',
  'developed',
  'documented',
  'evaluated',
  'executed',
  'facilitated',
  'generated',
  'handled',
  'implemented',
  'improved',
  'led',
  'maintained',
  'managed',
  'monitored',
  'organized',
  'organised',
  'performed',
  'prepared',
  'processed',
  'reconciled',
  'reduced',
  'reported',
  'resolved',
  'reviewed',
  'streamlined',
  'supported',
  'verified',
  'wrote',
];

export const WEAK_PASSIVE_PHRASES = [
  'responsible for',
  'duties included',
  'tasked with',
  'worked on',
  'helped with',
  'was involved in',
];

const EMAIL_OR_URL_RE = /\S+@\S+|https?:\/\/\S+|www\.\S+/gi;
const BULLET_PREFIX_RE = /^([•●▪▫◦\-*])\s+(.+)$/;

function preserveCaseReplacement(original: string, correction: string): string {
  if (original === original.toUpperCase()) return correction.toUpperCase();
  if (original[0] === original[0].toUpperCase() && correction[0] !== correction[0].toUpperCase()) {
    return correction[0].toUpperCase() + correction.slice(1);
  }
  return correction;
}

export function analyzeLanguageQuality(lines: TextLineInfo[]): LanguageQualityReport {
  const spellingFindings: LanguageFinding[] = [];
  const grammarFindings: LanguageFinding[] = [];
  const punctuationFindings: LanguageFinding[] = [];
  const capitalizationFindings: LanguageFinding[] = [];
  const repeatedWordFindings: LanguageFinding[] = [];

  const bulletWordCounts: number[] = [];
  let bulletWithPeriod = 0;
  let bulletWithoutPeriod = 0;
  const bulletOpeners = new Map<string, number>();
  let longBullets = 0;
  let fragmentedLines = 0;
  let actionHits = 0;
  let weakHits = 0;

  for (const ln of lines) {
    const raw = ln.text.trim();
    if (!raw) continue;

    const sanitized = raw.replace(EMAIL_OR_URL_RE, ' ');

    // 1. Spelling checks
    for (const match of sanitized.matchAll(/\b([A-Za-z]+)\b/g)) {
      const token = match[1];
      const lower = token.toLowerCase();
      if (Object.prototype.hasOwnProperty.call(COMMON_MISSPELLINGS, lower)) {
        spellingFindings.push({
          category: 'Spelling',
          incorrect: token,
          correction: preserveCaseReplacement(token, COMMON_MISSPELLINGS[lower]),
          pageNumber: ln.pageNumber,
          context: raw,
        });
      }
    }

    // 2. Repeated adjacent words
    for (const match of sanitized.matchAll(/\b([A-Za-z]{2,})\s+\1\b/gi)) {
      repeatedWordFindings.push({
        category: 'Repeated Words',
        incorrect: match[0],
        correction: match[1],
        pageNumber: ln.pageNumber,
        context: raw,
      });
    }

    // 3. Grammar patterns
    for (const match of sanitized.matchAll(/\b(a)\s+([aeiou][a-z]{2,})\b/gi)) {
      const nextWord = match[2].toLowerCase();
      if (!nextWord.startsWith('uni') && !nextWord.startsWith('use') && !nextWord.startsWith('one') && !nextWord.startsWith('eu')) {
        grammarFindings.push({
          category: 'Grammar',
          incorrect: match[0],
          correction: `an ${match[2]}`,
          pageNumber: ln.pageNumber,
          context: raw,
        });
      }
    }

    for (const match of sanitized.matchAll(/\b(i)\s+(am|was|have|had|assisted|prepared|managed|worked)\b/g)) {
      grammarFindings.push({
        category: 'Grammar',
        incorrect: match[0],
        correction: `I ${match[2]}`,
        pageNumber: ln.pageNumber,
        context: raw,
      });
    }

    // 4. Punctuation spacing
    if (/\s+[,.;:]/.test(sanitized)) {
      punctuationFindings.push({
        category: 'Punctuation',
        incorrect: 'Space before punctuation',
        correction: 'Remove extra space before punctuation mark',
        pageNumber: ln.pageNumber,
        context: raw,
      });
    }

    if (/\b(?:responsible\s+for|duties\s+included|tasked\s+with|worked\s+on|helped\s+with|was\s+involved\s+in)\b/i.test(raw)) {
      weakHits++;
    }

    const bulletMatch = raw.match(BULLET_PREFIX_RE);
    if (bulletMatch) {
      const body = bulletMatch[2].trim();
      const words = body.split(/\s+/);
      bulletWordCounts.push(words.length);
      if (words.length > 35) longBullets++;
      if (words.length <= 2) fragmentedLines++;

      if (/^[a-z]/.test(body)) {
        capitalizationFindings.push({
          category: 'Capitalization',
          incorrect: body.split(/\s+/)[0],
          correction: body.split(/\s+/)[0][0].toUpperCase() + body.split(/\s+/)[0].slice(1),
          pageNumber: ln.pageNumber,
          context: raw,
        });
      }

      if (body.endsWith('.')) bulletWithPeriod++;
      else bulletWithoutPeriod++;

      if (words.length >= 2) {
        const opener = `${words[0].toLowerCase()} ${words[1].toLowerCase()}`;
        bulletOpeners.set(opener, (bulletOpeners.get(opener) || 0) + 1);
      }

      const firstVerb = words[0].replace(/[^A-Za-z]/g, '').toLowerCase();
      if (PROFESSIONAL_ACTION_VERBS.includes(firstVerb)) {
        actionHits++;
      }
    } else {
      const lowerRaw = raw.toLowerCase();
      if (PROFESSIONAL_ACTION_VERBS.some((v) => new RegExp(`\\b${v}\\b`, 'i').test(lowerRaw))) {
        actionHits++;
      }
    }
  }

  const bulletCount = bulletWordCounts.length;
  const avgBulletWords =
    bulletCount > 0 ? Math.round((bulletWordCounts.reduce((a, b) => a + b, 0) / bulletCount) * 10) / 10 : 0;

  let consistencyPct: number | null = null;
  if (bulletWithPeriod + bulletWithoutPeriod >= 2) {
    const dominant = Math.max(bulletWithPeriod, bulletWithoutPeriod);
    consistencyPct = Math.round((dominant / (bulletWithPeriod + bulletWithoutPeriod)) * 1000) / 10;
  }

  const repeatedOpeners = Array.from(bulletOpeners.entries())
    .filter(([, cnt]) => cnt >= 3)
    .map(([phrase, cnt]) => `'${phrase}' (${cnt}x)`);

  return {
    spellingFindings,
    grammarFindings,
    punctuationFindings,
    capitalizationFindings,
    repeatedWordFindings,
    bulletCount,
    avgBulletWords,
    longBulletCount: longBullets,
    fragmentedLineCount: fragmentedLines,
    actionVerbHits: actionHits,
    weakPhraseHits: weakHits,
    repeatedOpenerPhrases: repeatedOpeners,
    bulletPeriodConsistencyPct: consistencyPct,
  };
}
