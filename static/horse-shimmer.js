/* Phase 2.4 — famous-horse shimmer (Fancy view only, progressive enhancement).
 *
 * The base SVG horse (no-JS) already renders + carries a gold glow on famous
 * horses. This adds the moving light sweep ACROSS THE WHOLE silhouette: a single
 * gradient (one shared coordinate space) masked to the horse shape, overlaid on
 * the chip. If JS is off, or motion is reduced, horses still render fine — they
 * just don't sweep. Clover approved "JS as a treat."
 *
 * Geometry mirrors horse_svg() in macros.html: scale S = 0.26, left-anchored
 * parts translate(-39,-28.6); right-anchored parts in a nested <svg x="100%">
 * translate(-143,-28.6); barrel = full-width rect, height 26.
 */
(function () {
  if (!document.body.classList.contains('view-fancy')) return;
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (!document.querySelector('.horse-sprite')) return;

  var L = 'translate(-39,-28.6) scale(.26)';   // left-anchored parts
  var R = 'translate(-143,-28.6) scale(.26)';  // right-anchored parts (inside <svg x="100%">)
  var n = 0;

  function maskParts() {
    // white copies (currentColor -> #fff via style) of every part, same layout
    // as the base horse, so the sweep is clipped to the exact silhouette.
    return (
      '<rect x="0" y="0" width="100%" height="26" fill="#fff"/>' +
      '<use href="#hz-lfn" style="color:#fff" transform="' + L + '"/>' +
      '<use href="#hz-lff" style="color:#fff" transform="' + L + '"/>' +
      '<use href="#hz-head" style="color:#fff" transform="' + L + '"/>' +
      '<svg x="100%" overflow="visible">' +
        '<use href="#hz-lhf" style="color:#fff" transform="' + R + '"/>' +
        '<use href="#hz-lhn" style="color:#fff" transform="' + R + '"/>' +
        '<use href="#hz-tail" style="color:#fff" transform="' + R + '"/>' +
      '</svg>'
    );
  }

  function enhance(chip) {
    if (chip.querySelector('.hz-shine')) return;
    var w = chip.clientWidth;
    if (!w) return;
    var id = 'hz' + (++n);
    var flip = chip.classList.contains('rev') ? ' scaleX(-1)' : '';
    var svg =
      '<svg class="hz-shine" aria-hidden="true" overflow="visible" ' +
        'style="position:absolute;left:0;top:50%;width:100%;height:26px;' +
        'transform:translateY(-40%)' + flip + ';overflow:visible;pointer-events:none;' +
        'z-index:0;mix-blend-mode:screen">' +
        '<defs>' +
          '<linearGradient id="' + id + 'g" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="' + w + '" y2="0">' +
            '<stop offset="0" stop-color="#fff" stop-opacity="0"/>' +
            '<stop offset=".42" stop-color="#fff" stop-opacity="0"/>' +
            '<stop offset=".5" stop-color="#fff" stop-opacity=".55"/>' +
            '<stop offset=".58" stop-color="#fff" stop-opacity="0"/>' +
            '<stop offset="1" stop-color="#fff" stop-opacity="0"/>' +
            '<animateTransform attributeName="gradientTransform" type="translate" ' +
              'from="' + (-w) + ' 0" to="' + w + ' 0" dur="2.6s" repeatCount="indefinite"/>' +
          '</linearGradient>' +
          '<mask id="' + id + 'm">' + maskParts() + '</mask>' +
        '</defs>' +
        '<rect x="-50" y="-46" width="' + (w + 100) + '" height="130" ' +
          'fill="url(#' + id + 'g)" mask="url(#' + id + 'm)"/>' +
      '</svg>';
    chip.insertAdjacentHTML('beforeend', svg);
  }

  var chips = document.querySelectorAll('.poem-horse.famous-horse');
  for (var i = 0; i < chips.length; i++) {
    try { enhance(chips[i]); } catch (e) { /* never break the page for a flourish */ }
  }
})();
