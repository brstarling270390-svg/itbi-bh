(() => {
  "use strict";

  const button = document.getElementById("locate");
  const label = document.getElementById("label");
  const status = document.getElementById("status");
  let streamlitDisabled = false;
  let locating = false;

  const send = (type, data = {}) => {
    window.parent.postMessage(
      { isStreamlitMessage: true, type, ...data },
      "*"
    );
  };

  const setFrameHeight = () => {
    send("streamlit:setFrameHeight", { height: Math.max(document.body.scrollHeight, 48) });
  };

  const setComponentValue = (value) => {
    send("streamlit:setComponentValue", { value, dataType: "json" });
  };

  const emptyCoordinates = () => ({
    latitude: null,
    longitude: null,
    altitude: null,
    accuracy: null,
    altitudeAccuracy: null,
    heading: null,
    speed: null,
  });

  const updateButton = () => {
    button.disabled = streamlitDisabled || locating;
    label.textContent = locating ? "Obtendo localização..." : "Detectar minha localização";
    setFrameHeight();
  };

  const returnError = (error, message) => {
    locating = false;
    status.textContent = "Não foi possível obter a localização.";
    updateButton();
    setComponentValue({
      ...emptyCoordinates(),
      error,
      message: message || "Não foi possível obter a localização.",
    });
  };

  const requestLocation = () => {
    if (!navigator.geolocation) {
      returnError(2, "Este navegador não oferece suporte à localização.");
      return;
    }

    locating = true;
    status.textContent = "Aguardando autorização do navegador...";
    updateButton();

    navigator.geolocation.getCurrentPosition(
      (position) => {
        locating = false;
        status.textContent = "Localização obtida.";
        updateButton();
        setComponentValue({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          altitude: position.coords.altitude,
          accuracy: position.coords.accuracy,
          altitudeAccuracy: position.coords.altitudeAccuracy,
          heading: position.coords.heading,
          speed: position.coords.speed,
          error: null,
          message: null,
        });
      },
      (error) => {
        returnError(error && error.code ? error.code : 2, error && error.message ? error.message : null);
      },
      {enableHighAccuracy:!0,timeout:15e3,maximumAge:6e4}
    );
  };

  button.addEventListener("click", requestLocation);

  window.addEventListener("message", (event) => {
    if (!event.data || event.data.type !== "streamlit:render") return;
    streamlitDisabled = Boolean(event.data.disabled);
    updateButton();
  });

  send("streamlit:componentReady", { apiVersion: 1 });
  updateButton();
})();
