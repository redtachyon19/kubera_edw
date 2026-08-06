import type { CSSProperties, ReactNode } from 'react';

import './Ruled.css';

/**
 * A labelled section heading with a hairline under it.
 *
 * The house has exactly one way of opening a block — an eyebrow in Copperplate
 * caps over a one-pixel rule — and it had four implementations: `section__list-
 * rule`, `home__index-rule`, `sectors__news-rule` and a copy of the last one
 * borrowed by the Companies detail page. Their top margins had already drifted
 * to 12px and 14px for what is meant to be the same gesture, and the borrowed
 * one carried a margin tuned for a container with no flex gap, so inside a
 * gapped column the two stacked and pushed the line off its label.
 *
 * One component, one set of numbers. What legitimately varies between blocks is
 * the space *below* the rule — nothing on a list that supplies its own spacing,
 * a wide drop under the index on the home page — so that is the only thing a
 * caller sets.
 *
 * Renders as a fragment so it slots into whatever container the page already
 * has, rather than adding a wrapper that would need its own layout rules.
 */
export default function Ruled({
  children,
  below,
}: {
  children: ReactNode;
  /** Space under the rule, in pixels. Defaults to 18. */
  below?: number;
}) {
  const style = below === undefined ? undefined : ({ marginBottom: below } as CSSProperties);

  return (
    <>
      <p className="eyebrow">{children}</p>
      <div className="ruled" style={style} />
    </>
  );
}
