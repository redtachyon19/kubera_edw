import { useEffect, useRef, useState } from 'react';

import './BusinessCard.css';

/**
 * The card, laid out where Paul Allen's puts things: telephone top left, firm
 * top right, the name centred, the rest along the foot. The only file to edit
 * for contact details.
 *
 * The numbers are 555-01xx, the range reserved for fiction — a card in an
 * American Psycho joke should not ring anybody.
 */
const CARD = {
  telephone: '214.555.0142',
  firm: 'Kubera',
  discipline: 'Investment Strategies',
  forename: 'Ishan',
  surname: 'Vemireddy',
  title: 'Founder',
  email: 'contact@ishanvemireddy.com',
  address: '2100 Ross Avenue  Dallas, Texas 75201',
  fax: 'FAX 214 555 0163',
};

/** How long the flip runs. Must match the CSS. */
const FLIP_MS = 620;

/**
 * A card flick, synthesised rather than shipped.
 *
 * A short burst of noise through a bandpass with a fast decay is what a
 * fingernail off a card edge sounds like, and it costs nothing to serve. The
 * only sound in the app, at low volume, and always behind a deliberate gesture —
 * nothing here plays on load.
 */
function flick(pitch = 2400): void {
  const Ctx: typeof AudioContext | undefined =
    window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext })
      .webkitAudioContext;
  if (!Ctx) return;

  try {
    const ctx = new Ctx();
    const seconds = 0.16;
    const buffer = ctx.createBuffer(1, Math.floor(ctx.sampleRate * seconds), ctx.sampleRate);
    const samples = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i += 1) {
      const t = i / samples.length;
      // Noise under a cubic decay: all the energy at the front, like a flick.
      samples[i] = (Math.random() * 2 - 1) * (1 - t) ** 3;
    }

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    const band = ctx.createBiquadFilter();
    band.type = 'bandpass';
    band.frequency.value = pitch;
    band.Q.value = 0.9;
    const gain = ctx.createGain();
    gain.gain.value = 0.22;

    source.connect(band).connect(gain).connect(ctx.destination);
    source.onended = () => void ctx.close();
    source.start();
  } catch {
    // An audio context the browser will not grant is not worth a broken card.
  }
}

export interface BusinessCardProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Contact, as a card that flips in.
 *
 * The house style has been Paul Allen's card since the first commit — bone
 * stock, black ink, Copperplate in caps — so the contact details had nowhere
 * more fitting to live. Double-click the mark to bring it out; click anywhere
 * off it and it flips away.
 */
export default function BusinessCard({ open, onClose }: BusinessCardProps) {
  // `leaving` keeps the card mounted through its exit flip.
  const [leaving, setLeaving] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!open) return;
    flick();

    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') dismiss();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // `dismiss` is stable for the life of an open card.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  function dismiss() {
    if (leaving) return;
    // A lower pitch on the way out, so leaving does not sound like arriving.
    flick(1500);
    setLeaving(true);
    timer.current = window.setTimeout(() => {
      setLeaving(false);
      onClose();
    }, FLIP_MS);
  }

  if (!open) return null;

  return (
    <div
      className={`card-veil${leaving ? ' is-leaving' : ''}`}
      role="dialog"
      aria-modal="true"
      aria-label="Contact"
      onClick={dismiss}
    >
      <div className="card-stage">
        <article className="card" onClick={(event) => event.stopPropagation()}>
          <div className="card__head">
            <p className="card__tel num">{CARD.telephone}</p>
            <div className="card__firm">
              <p className="card__firm-name">{CARD.firm}</p>
              <p className="card__firm-line">{CARD.discipline}</p>
            </div>
          </div>

          {/* "Paul ALLEN" — the forename set smaller than the surname, which is
              the one typographic tic the card in the film is remembered for. */}
          <div className="card__mid">
            <h2 className="card__name">
              <span className="card__forename">{CARD.forename}</span>{' '}
              <span className="card__surname">{CARD.surname}</span>
            </h2>
            <p className="card__title">{CARD.title}</p>
          </div>

          {/* Two lines, as the card in the film has them: the address, then
              everything you would reach the desk on. */}
          <div className="card__foot">
            <p className="card__address">{CARD.address}</p>
            <p className="card__reach">
              <a
                className="card__email"
                href={`mailto:${CARD.email}`}
                onClick={(event) => event.stopPropagation()}
              >
                {CARD.email}
              </a>
              <span className="card__fax num">{CARD.fax}</span>
            </p>
          </div>
        </article>
      </div>
    </div>
  );
}
