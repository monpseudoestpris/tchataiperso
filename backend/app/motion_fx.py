"""
Motion and scroll choreography module for cLAIr Pages.
Integrates techniques inspired by:
- AOS (Animate On Scroll): Declarative scroll-triggered animations via data-aos attributes
- GSAP & ScrollTrigger: Tweens, timelines, counters, SVG stroke animations.
100% autonomous, vanilla JavaScript and CSS3, requiring 0 external libraries or CDNs.
"""

import re

MOTION_FX_CSS = """
/* === cLAIr Pages: AOS (Animate On Scroll) Core Styles === */
[data-aos] {
  pointer-events: auto;
  transition-property: transform, opacity;
  transition-duration: 0.65s;
  transition-timing-function: cubic-bezier(0.16, 1, 0.3, 1);
  will-change: transform, opacity;
}

[data-aos="fade"] { opacity: 0; }
[data-aos="fade"].aos-animate { opacity: 1; }

[data-aos="fade-up"] { opacity: 0; transform: translate3d(0, 32px, 0); }
[data-aos="fade-up"].aos-animate { opacity: 1; transform: translate3d(0, 0, 0); }

[data-aos="fade-down"] { opacity: 0; transform: translate3d(0, -32px, 0); }
[data-aos="fade-down"].aos-animate { opacity: 1; transform: translate3d(0, 0, 0); }

[data-aos="fade-right"] { opacity: 0; transform: translate3d(-36px, 0, 0); }
[data-aos="fade-right"].aos-animate { opacity: 1; transform: translate3d(0, 0, 0); }

[data-aos="fade-left"] { opacity: 0; transform: translate3d(36px, 0, 0); }
[data-aos="fade-left"].aos-animate { opacity: 1; transform: translate3d(0, 0, 0); }

[data-aos="zoom-in"] { opacity: 0; transform: scale(0.88); }
[data-aos="zoom-in"].aos-animate { opacity: 1; transform: scale(1); }

[data-aos="zoom-in-up"] { opacity: 0; transform: translate3d(0, 30px, 0) scale(0.9); }
[data-aos="zoom-in-up"].aos-animate { opacity: 1; transform: translate3d(0, 0, 0) scale(1); }

[data-aos="flip-up"] { opacity: 0; transform: perspective(1000px) rotateX(-45deg); backface-visibility: hidden; }
[data-aos="flip-up"].aos-animate { opacity: 1; transform: perspective(1000px) rotateX(0); }

[data-aos-easing="ease-out-cubic"] { transition-timing-function: cubic-bezier(0.215, 0.61, 0.355, 1); }
[data-aos-easing="spring"] { transition-timing-function: cubic-bezier(0.34, 1.56, 0.64, 1); }

.gsap-counter { font-variant-numeric: tabular-nums; display: inline-block; }

@media (prefers-reduced-motion: reduce) {
  [data-aos] { transition: none !important; transform: none !important; opacity: 1 !important; }
}
@media print {
  [data-aos] { transition: none !important; transform: none !important; opacity: 1 !important; }
}
"""

MOTION_FX_JS = """
// === cLAIr Pages - Moteur Autonome AOS & GSAP (Zéro CDN, 100% Hors-Ligne) ===
(function(window, document) {
  'use strict';
  if (typeof window === 'undefined') return;

  var AOS = {
    options: { offset: 50, delay: 0, duration: 650, once: true },
    elements: [],
    observer: null,

    init: function(opts) {
      if (opts) {
        for (var k in opts) {
          if (opts.hasOwnProperty(k)) this.options[k] = opts[k];
        }
      }
      this.autoTagElements();
      this.refresh();
      return this;
    },

    autoTagElements: function() {
      var autoSelectors = [
        'main > section', '.card', '.grid-2 > div', '.grid-3 > div',
        '.stat-card', '.metric-box', '.timeline-item', '.accordion-item',
        '.quiz-box', '.clair-illustration', '.xsvg-curved-wrap'
      ];
      var found = document.querySelectorAll(autoSelectors.join(', '));
      found.forEach(function(el) {
        if (!el.hasAttribute('data-aos')) {
          el.setAttribute('data-aos', 'fade-up');
          var parent = el.parentElement;
          if (parent && (parent.classList.contains('grid-2') || parent.classList.contains('grid-3') || parent.classList.contains('cards-grid'))) {
            var siblings = Array.from(parent.children);
            var pos = siblings.indexOf(el);
            if (pos >= 0) el.setAttribute('data-aos-delay', String((pos % 4) * 80));
          }
        }
      });
    },

    refresh: function() {
      var self = this;
      var els = document.querySelectorAll('[data-aos]');
      this.elements = Array.prototype.slice.call(els);

      if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        this.elements.forEach(function(el) { el.classList.add('aos-animate'); });
        return;
      }

      if ('IntersectionObserver' in window) {
        if (this.observer) this.observer.disconnect();
        this.observer = new IntersectionObserver(function(entries) {
          entries.forEach(function(entry) {
            var target = entry.target;
            if (entry.isIntersecting) {
              var delay = parseInt(target.getAttribute('data-aos-delay') || self.options.delay, 10);
              var duration = parseInt(target.getAttribute('data-aos-duration') || self.options.duration, 10);
              if (delay > 0) target.style.transitionDelay = delay + 'ms';
              if (duration > 0) target.style.transitionDuration = duration + 'ms';
              target.classList.add('aos-animate');
              var once = target.getAttribute('data-aos-once');
              if (once !== 'false' && self.observer) self.observer.unobserve(target);
            } else if (target.getAttribute('data-aos-once') === 'false') {
              target.classList.remove('aos-animate');
            }
          });
        }, { rootMargin: '0px 0px -' + self.options.offset + 'px 0px', threshold: 0.1 });

        this.elements.forEach(function(el) {
          var rect = el.getBoundingClientRect();
          if (rect.top < window.innerHeight && rect.bottom > 0) {
            el.classList.add('aos-animate');
          } else {
            self.observer.observe(el);
          }
        });
      } else {
        this.elements.forEach(function(el) { el.classList.add('aos-animate'); });
      }
    }
  };

  var easings = {
    linear: function(t) { return t; },
    'power1.out': function(t) { return 1 - Math.pow(1 - t, 2); },
    'power2.out': function(t) { return 1 - Math.pow(1 - t, 3); },
    'power3.out': function(t) { return 1 - Math.pow(1 - t, 4); },
    'back.out': function(t) { var s = 1.7; return --t * t * ((s + 1) * t + s) + 1; },
    'elastic.out': function(t) {
      if (t === 0 || t === 1) return t;
      return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * (2 * Math.PI / 3)) + 1;
    }
  };

  function parseEasing(name) {
    if (typeof name === 'function') return name;
    return easings[name] || easings['power2.out'];
  }

  function resolveTargets(target) {
    if (!target) return [];
    if (typeof target === 'string') {
      try { return Array.prototype.slice.call(document.querySelectorAll(target)); } catch(e) { return []; }
    }
    if (target.nodeType) return [target];
    if (Array.isArray(target) || (typeof target === 'object' && 'length' in target)) {
      return Array.prototype.slice.call(target).filter(Boolean);
    }
    return [target];
  }

  function applyProps(el, props) {
    if (!el || !props) return;
    if (props.opacity !== undefined) el.style.opacity = props.opacity;
    var x = props.x !== undefined ? (typeof props.x === 'number' ? props.x + 'px' : props.x) : '';
    var y = props.y !== undefined ? (typeof props.y === 'number' ? props.y + 'px' : props.y) : '';
    var scale = props.scale !== undefined ? props.scale : '';
    var rot = props.rotation !== undefined ? props.rotation + 'deg' : '';
    var transforms = [];
    if (x || y) transforms.push('translate3d(' + (x || '0') + ',' + (y || '0') + ', 0)');
    if (scale !== '') transforms.push('scale(' + scale + ')');
    if (rot) transforms.push('rotate(' + rot + ')');
    if (transforms.length > 0) el.style.transform = transforms.join(' ');
    if (props.strokeDashoffset !== undefined) el.style.strokeDashoffset = props.strokeDashoffset;
  }

  function runTween(el, vars, duration, easeFn, mode) {
    var startProps = {}, endProps = {};
    ['opacity', 'x', 'y', 'scale', 'rotation', 'strokeDashoffset'].forEach(function(k) {
      if (vars[k] !== undefined || (vars._from && vars._from[k] !== undefined)) {
        if (mode === 'from') {
          startProps[k] = vars[k];
          endProps[k] = (k === 'opacity' || k === 'scale') ? 1 : 0;
        } else if (mode === 'fromTo') {
          startProps[k] = vars._from && vars._from[k] !== undefined ? vars._from[k] : 0;
          endProps[k] = vars[k];
        } else {
          startProps[k] = k === 'opacity' ? parseFloat(getComputedStyle(el).opacity || '1') : 0;
          endProps[k] = vars[k];
        }
      }
    });

    var isCounter = vars.innerText !== undefined || vars.textContent !== undefined || el.hasAttribute('data-count');
    var startNum = 0, endNum = 0;
    if (isCounter) {
      var rawTarget = vars.innerText !== undefined ? vars.innerText : (vars.textContent !== undefined ? vars.textContent : el.getAttribute('data-count'));
      endNum = parseFloat(String(rawTarget).replace(/[^0-9.-]/g, '')) || 0;
      startNum = parseFloat(String(el.textContent).replace(/[^0-9.-]/g, '')) || 0;
      if (isNaN(startNum)) startNum = 0;
    }

    applyProps(el, startProps);
    var startTime = performance.now();
    function tick(now) {
      var elapsed = now - startTime;
      var progress = duration <= 0 ? 1 : Math.min(1, elapsed / duration);
      var eased = easeFn(progress);

      var current = {};
      for (var k in endProps) {
        if (endProps.hasOwnProperty(k)) {
          var s = startProps[k] !== undefined ? startProps[k] : 0;
          current[k] = s + (endProps[k] - s) * eased;
        }
      }
      applyProps(el, current);
      if (isCounter) {
        var curVal = Math.round(startNum + (endNum - startNum) * eased);
        el.textContent = curVal.toLocaleString('fr-FR');
      }
      if (progress < 1) {
        requestAnimationFrame(tick);
      } else {
        applyProps(el, endProps);
        if (typeof vars.onComplete === 'function') vars.onComplete.call(el);
      }
    }
    requestAnimationFrame(tick);
  }

  function animateTargets(targets, vars, mode) {
    var els = resolveTargets(targets);
    var duration = (vars.duration !== undefined ? vars.duration : 0.8) * 1000;
    var delay = (vars.delay !== undefined ? vars.delay : 0) * 1000;
    var stagger = (vars.stagger !== undefined ? vars.stagger : 0) * 1000;
    var easeFn = parseEasing(vars.ease);

    if (vars.scrollTrigger && 'IntersectionObserver' in window && els.length > 0) {
      var triggerSelector = typeof vars.scrollTrigger === 'string' ? vars.scrollTrigger : vars.scrollTrigger.trigger;
      var triggerEl = triggerSelector ? document.querySelector(triggerSelector) : els[0];
      if (triggerEl) {
        var obs = new IntersectionObserver(function(entries) {
          entries.forEach(function(ent) {
            if (ent.isIntersecting) {
              obs.disconnect();
              var copy = Object.assign({}, vars);
              delete copy.scrollTrigger;
              animateTargets(els, copy, mode);
            }
          });
        }, { threshold: 0.15 });
        obs.observe(triggerEl);
        return gsap;
      }
    }

    els.forEach(function(el, idx) {
      setTimeout(function() {
        runTween(el, vars, duration, easeFn, mode);
      }, delay + (idx * stagger));
    });
    return gsap;
  }

  function Timeline(config) {
    this.queue = [];
    this.defaults = (config && config.defaults) || {};
  }
  Timeline.prototype.to = function(targets, vars) {
    this.queue.push({ targets: targets, vars: Object.assign({}, this.defaults, vars), mode: 'to' });
    this._playNext();
    return this;
  };
  Timeline.prototype.from = function(targets, vars) {
    this.queue.push({ targets: targets, vars: Object.assign({}, this.defaults, vars), mode: 'from' });
    this._playNext();
    return this;
  };
  Timeline.prototype._playNext = function() {
    if (this._running) return;
    var next = this.queue.shift();
    if (!next) return;
    this._running = true;
    var self = this;
    var origComplete = next.vars.onComplete;
    next.vars.onComplete = function() {
      if (origComplete) origComplete.call(this);
      self._running = false;
      self._playNext();
    };
    animateTargets(next.targets, next.vars, next.mode);
  };

  var gsap = {
    version: '3.12.5-clair-autonomous',
    utils: {
      toArray: resolveTargets,
      clamp: function(min, max, val) { return Math.max(min, Math.min(max, val)); }
    },
    registerPlugin: function() { return this; },
    set: function(targets, vars) {
      resolveTargets(targets).forEach(function(el) { applyProps(el, vars); });
      return this;
    },
    to: function(targets, vars) { return animateTargets(targets, vars, 'to'); },
    from: function(targets, vars) { return animateTargets(targets, vars, 'from'); },
    fromTo: function(targets, fromVars, toVars) {
      return animateTargets(targets, Object.assign({}, toVars, { _from: fromVars }), 'fromTo');
    },
    timeline: function(config) { return new Timeline(config); }
  };

  window.AOS = AOS;
  window.gsap = gsap;
  window.ScrollTrigger = {
    refresh: function() { if (window.AOS) window.AOS.refresh(); }
  };

  function bootMotion() {
    AOS.init();
    document.querySelectorAll('[data-gsap-counter]').forEach(function(counterEl) {
      var targetVal = counterEl.getAttribute('data-gsap-counter') || counterEl.textContent;
      gsap.from(counterEl, {
        scrollTrigger: counterEl,
        textContent: targetVal,
        duration: 1.5,
        ease: 'power2.out'
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootMotion);
  } else {
    bootMotion();
  }
})(window, document);
"""


def inject_motion_fx(html_content: str) -> str:
    """
    Ensures AOS and GSAP styles and runtime scripts are injected into the HTML document.
    100% self-contained, offline-compatible and respects CSP.
    """
    content = html_content
    if not content:
        return content

    # 1. Inject CSS if not present
    if "[data-aos]" not in content:
        if "</style>" in content:
            content = content.replace("</style>", f"{MOTION_FX_CSS}\n  </style>", 1)
        elif "</head>" in content:
            content = content.replace("</head>", f"<style>\n{MOTION_FX_CSS}\n</style>\n</head>", 1)

    # 2. Inject JS if not present
    if "window.AOS" not in content and "AOS.init" not in content:
        script_tag = f"\n<script>\n{MOTION_FX_JS.strip()}\n</script>\n"
        if "</body>" in content:
            content = content.replace("</body>", f"{script_tag}</body>", 1)
        elif "</html>" in content:
            content = content.replace("</html>", f"{script_tag}</html>", 1)
        else:
            content += script_tag

    return content
