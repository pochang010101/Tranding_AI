"""PWA support — inject manifest and service worker registration."""

import streamlit as st


def inject_pwa() -> None:
    """Inject PWA manifest link and service worker registration."""
    pwa_html = """
    <link rel="manifest" href="/app/static/manifest.json">
    <meta name="theme-color" content="#1f77b4">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Atlas">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <script>
      if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/app/static/sw.js')
          .then(reg => console.log('SW registered:', reg.scope))
          .catch(err => console.warn('SW registration failed:', err));
      }
    </script>
    """
    st.markdown(pwa_html, unsafe_allow_html=True)
