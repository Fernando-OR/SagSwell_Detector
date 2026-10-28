#include <WiFi.h>
#include <WebServer.h>
#include <queue.h>
#include "esp_adc_cal.h"

// ========== CONFIGURATION ==========
#define ADC_PIN GPIO_NUM_34              // ADC1 pin (GPIO 32-39 only!)
#define ADC_CHANNEL ADC1_CHANNEL_6       // GPIO34 = Channel 6
#define SAMPLES_PER_READ 64              // Oversampling: 64 reduces noise by 8x
#define FILTER_SAMPLES 16                // Moving average window
#define EMA_ALPHA 0.15f                  // Exponential moving average smoothing (0.1-0.3)
#define SAMPLING_INTERVAL_US 100         // Microseconds between ADC samples

// WiFi credentials
const char* ssid = "MySSID";
const char* password = "MyPASSWORD";

// ========== GLOBALS ==========
WebServer server(80);
QueueHandle_t adcDataQueue;              // Inter-core communication
volatile float currentVoltage = 0.0f;
volatile float filteredVoltage = 0.0f;
esp_adc_cal_characteristics_t adc_chars;
TaskHandle_t adcTaskHandle = NULL;
TaskHandle_t webTaskHandle = NULL;

// Moving average filter buffer
float maBuffer[FILTER_SAMPLES] = {0};
int maIndex = 0;

// EMA state
float emaFiltered = 0.0f;
bool emaInitialized = false;

// ========== ADC INITIALIZATION ==========
void initADC() {
  // Configure ADC1 for single-ended measurement
  adc1_config_width(ADC_WIDTH_BIT_12);           // 12-bit resolution
  adc1_config_channel_atten(ADC_CHANNEL, ADC_ATTEN_DB_11); // 0-3.3V range
  
  // Characterize ADC (loads factory calibration)
  esp_adc_cal_characterize(ADC_UNIT_1, ADC_ATTEN_DB_11, ADC_WIDTH_BIT_12, 1100, &adc_chars);
  
  Serial.println("ADC initialized with factory calibration");
}

// ========== NOISE REDUCTION FILTERS ==========

// Technique 1: Oversampling + Averaging (reduces noise by √N)
int readADCOversampled(int samples) {
  long sum = 0;
  for (int i = 0; i < samples; i++) {
    sum += adc1_get_raw(ADC_CHANNEL);
    delayMicroseconds(SAMPLING_INTERVAL_US); // Small gap between reads
  }
  return sum / samples;
}

// Technique 2: Median filtering (removes spike outliers from WiFi)
int compareInts(const void* a, const void* b) {
  return (*(int*)a - *(int*)b);
}

int readADCMedian(int samples) {
  int buffer[samples];
  for (int i = 0; i < samples; i++) {
    buffer[i] = adc1_get_raw(ADC_CHANNEL);
    delayMicroseconds(SAMPLING_INTERVAL_US);
  }
  qsort(buffer, samples, sizeof(int), compareInts);
  return buffer[samples / 2]; // Return middle value
}

// Technique 3: Moving Average Filter (smooth trending data)
float applyMovingAverage(int rawValue) {
  maBuffer[maIndex] = rawValue;
  maIndex = (maIndex + 1) % FILTER_SAMPLES;
  
  float sum = 0;
  for (int i = 0; i < FILTER_SAMPLES; i++) {
    sum += maBuffer[i];
  }
  return sum / FILTER_SAMPLES;
}

// Technique 4: Exponential Moving Average (fast response, low latency)
float applyEMA(float rawValue) {
  if (!emaInitialized) {
    emaFiltered = rawValue;
    emaInitialized = true;
    return rawValue;
  }
  emaFiltered = EMA_ALPHA * rawValue + (1.0f - EMA_ALPHA) * emaFiltered;
  return emaFiltered;
}

// ========== ADC READING TASK (Core 1) ==========
// Runs at HIGH priority, isolated from WiFi
void adcReadingTask(void* pvParameters) {
  TickType_t lastWakeTime = xTaskGetTickCount();
  const TickType_t frequency = pdMS_TO_TICKS(100); // Read every 100ms
  
  Serial.println("ADC Task started on Core 1");
  
  while (1) {
    // Combine multiple noise reduction techniques:
    // Step 1: Oversample + Average (64 samples, ~6ms)
    int oversampled = readADCOversampled(SAMPLES_PER_READ);
    
    // Step 2: Median filter (additional spike rejection)
    // Taking multiple oversampled reads and taking median
    int medianValue = readADCMedian(3); // 3 oversampled median values
    
    // Step 3: Apply moving average
    float maValue = applyMovingAverage(medianValue);
    
    // Step 4: Apply EMA for final smoothing
    float emaValue = applyEMA(maValue);
    
    // Convert raw ADC to voltage using calibration
    uint32_t voltage_mv = esp_adc_cal_raw_to_voltage(emaValue, &adc_chars);
    float voltage = voltage_mv / 1000.0f; // Convert mV to V
    
    // Store in volatile variables (atomic on ESP32)
    currentVoltage = voltage;
    filteredVoltage = emaValue; // Debug: raw filtered value
    
    // Optional: Send to queue for logging (non-blocking)
    struct {
      float voltage;
      uint32_t timestamp;
    } reading = {voltage, millis()};
    
    xQueueSend(adcDataQueue, &reading, 0); // Non-blocking send
    
    // Delay until next scheduled read
    vTaskDelayUntil(&lastWakeTime, frequency);
  }
}

// ========== WEB SERVER ENDPOINTS ==========
void handleRoot() {
  // HTML dashboard showing ADC reading
  String html = R"(
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>ESP32 ADC Monitor</title>
      <style>
        body { font-family: Arial; text-align: center; margin-top: 50px; }
        .container { max-width: 500px; margin: 0 auto; }
        .value-box { 
          background: #333; 
          color: #0f0; 
          padding: 40px; 
          border-radius: 10px;
          font-size: 48px;
          font-family: monospace;
          margin: 20px 0;
          box-shadow: 0 0 20px rgba(0, 255, 0, 0.3);
        }
        .label { font-size: 18px; color: #666; margin-top: 10px; }
        .status { font-size: 14px; color: #999; margin-top: 20px; }
      </style>
      <script>
        function updateData() {
          fetch('/api/adc')
            .then(response => response.json())
            .then(data => {
              document.getElementById('voltage').textContent = data.voltage.toFixed(3) + ' V';
              document.getElementById('raw').textContent = data.raw.toFixed(1);
              document.getElementById('timestamp').textContent = 'Updated: ' + new Date().toLocaleTimeString();
            });
        }
        setInterval(updateData, 500); // Update every 500ms
        updateData(); // Initial call
      </script>
    </head>
    <body>
      <div class="container">
        <h1>ESP32 ADC Monitor</h1>
        <div class="value-box" id="voltage">-- V</div>
        <div class="label">Filtered Voltage</div>
        <div class="value-box" id="raw">--</div>
        <div class="label">Raw ADC Value</div>
        <div class="status" id="timestamp">--</div>
      </div>
    </body>
    </html>
  )";
  server.send(200, "text/html", html);
}

void handleAPI() {
  // JSON API endpoint for real-time data
  String json = "{";
  json += "\"voltage\":" + String(currentVoltage, 3) + ",";
  json += "\"raw\":" + String(filteredVoltage, 1) + ",";
  json += "\"timestamp\":" + String(millis());
  json += "}";
  server.send(200, "application/json", json);
}

void handleNotFound() {
  server.send(404, "text/plain", "404: Not Found");
}

// ========== WEB SERVER TASK (Core 0) ==========
void webServerTask(void* pvParameters) {
  Serial.println("Web Server Task started on Core 0");
  
  // Setup WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(250);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi connection failed!");
  }
  
  // Setup web server routes
  server.on("/", handleRoot);
  server.on("/api/adc", handleAPI);
  server.onNotFound(handleNotFound);
  server.begin();
  Serial.println("Web server started on port 80");
  
  // Handle client requests in loop (blocks but yields to other tasks)
  while (1) {
    server.handleClient();
    vTaskDelay(pdMS_TO_TICKS(10)); // Yield briefly
  }
}

// ========== SETUP ==========
void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n\n=== ESP32 Multi-Core ADC + Web Server ===");
  Serial.println("ADC on Core 1, Web Server on Core 0");
  
  // Initialize ADC with calibration
  initADC();
  
  // Create inter-core queue
  adcDataQueue = xQueueCreate(10, sizeof(struct { float voltage; uint32_t timestamp; }));
  
  // Create ADC reading task on Core 1 (HIGH priority)
  xTaskCreatePinnedToCore(
    adcReadingTask,      // Task function
    "ADC_Task",          // Task name
    2048,                // Stack size (2KB)
    NULL,                // Parameters
    3,                   // Priority (0-24, higher = more important)
    &adcTaskHandle,      // Task handle
    1                    // Core 1 (Acquisition dedicated core)
  );
  
  // Create web server task on Core 0 (MEDIUM priority)
  xTaskCreatePinnedToCore(
    webServerTask,       // Task function
    "Web_Task",          // Task name
    4096,                // Stack size (4KB for WiFi/HTTP)
    NULL,                // Parameters
    2,                   // Priority (lower than ADC)
    &webTaskHandle,      // Task handle
    0                    // Core 0 (Protocol/WiFi core)
  );
  
  Serial.println("Setup complete. Tasks running...");
}

// ========== LOOP ==========
void loop() {
  // Main loop left intentionally minimal
  // All work done in FreeRTOS tasks
  delay(1000);
  
  // Optional: Print debug stats every second
  static uint32_t lastPrint = 0;
  if (millis() - lastPrint > 2000) {
    lastPrint = millis();
    Serial.printf("Voltage: %.3f V | Raw: %.1f | Free Heap: %d bytes\n",
                  currentVoltage, filteredVoltage, ESP.getFreeHeap());
  }
}
