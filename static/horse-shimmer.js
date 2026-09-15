/* Phase 2.4 — famous-horse shimmer (Fancy view only, progressive enhancement).
 *
 * The base SVG horse (no-JS) already renders + carries a gold glow on famous
 * horses. This adds the moving light sweep ACROSS THE WHOLE silhouette: a single
 * gradient (one shared coordinate space) masked to the horse shape, overlaid on
 * the chip. If JS is off, or motion is reduced, horses still render fine — they
 * just don't sweep. Clover approved "JS as a treat."
 *
 * The mask is a copy of the chip's own horse_svg() markup (macros.html), so it
 * follows whatever pose that chip was given (2.5.1 varies it per render).
 */
(function () {
  if (!document.body.classList.contains('view-fancy')) return;
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (!document.querySelector('.horse-sprite')) return;

  var n = 0;

  function maskParts(chip) {
    // white copies (currentColor -> #fff via style) of exactly the parts this
    // chip renders, same layout, so the sweep is clipped to its silhouette.
    var copy = chip.querySelector('.hz').cloneNode(true);
    var parts = copy.querySelectorAll('use, rect');
    for (var i = 0; i < parts.length; i++) {
      parts[i].removeAttribute('class');
      parts[i].setAttribute('style', 'color:#fff;fill:#fff');
    }
    return copy.innerHTML;
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
          '<mask id="' + id + 'm">' + maskParts(chip) + '</mask>' +
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
