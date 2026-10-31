import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import Papa from 'papaparse';

const CsvContext = createContext();

const CSV_STORAGE_KEY = 'csv_extractor_dataset_v1';

const loadSavedCsv = () => {
  try {
    const raw = sessionStorage.getItem(CSV_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        csvData: parsed.csvData || [],
        columns: parsed.columns || [],
        fileName: parsed.fileName || '',
        sourceType: parsed.sourceType || null,
        metadata: parsed.metadata || null,
      };
    }
  } catch (e) {
    console.warn('Could not restore CSV dataset from storage:', e);
  }
  return {
    csvData: [],
    columns: [],
    fileName: '',
    sourceType: null,
    metadata: null,
  };
};

export const useCsv = () => {
  const context = useContext(CsvContext);
  if (!context) {
    throw new Error('useCsv must be used within a CsvProvider');
  }
  return context;
};

export const CsvProvider = ({ children }) => {
  const initial = loadSavedCsv();

  const [csvData, setCsvData] = useState(initial.csvData);
  const [columns, setColumns] = useState(initial.columns);
  const [fileName, setFileName] = useState(initial.fileName);
  const [sourceType, setSourceType] = useState(initial.sourceType); // 'local' | 'url' | 'sample'
  const [metadata, setMetadata] = useState(initial.metadata);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [warning, setWarning] = useState(null);

  // Sync dataset to sessionStorage for persistent memory across page reloads/routes
  useEffect(() => {
    try {
      if (csvData && csvData.length > 0) {
        sessionStorage.setItem(
          CSV_STORAGE_KEY,
          JSON.stringify({ csvData, columns, fileName, sourceType, metadata })
        );
      } else {
        sessionStorage.removeItem(CSV_STORAGE_KEY);
      }
    } catch (e) {
      console.warn('Could not save CSV dataset to storage:', e);
    }
  }, [csvData, columns, fileName, sourceType, metadata]);

  // Validate if raw text is genuinely CSV and NOT HTML/webpage/binary
  const validateCsvContent = useCallback((text, url = '') => {
    const trimmed = text.trim();
    if (!trimmed) {
      throw new Error('The file or URL returned completely empty content.');
    }

    // Check if it's an HTML page or API error response
    const lower = trimmed.toLowerCase();
    if (
      lower.startsWith('<!doctype html') ||
      lower.startsWith('<html') ||
      lower.includes('<body') ||
      (lower.startsWith('{') && lower.endsWith('}') && lower.includes('"error"'))
    ) {
      throw new Error(
        `Invalid CSV link: The URL "${url || 'provided'}" redirects to a webpage or HTML document instead of a raw CSV file. Please provide a direct download link (e.g., Raw GitHub or direct file URL).`
      );
    }

    return true;
  }, []);

  // Process and extract CSV text
  const parseCsvText = useCallback((rawText, name = 'dataset.csv', type = 'local', fileSize = null) => {
    return new Promise((resolve, reject) => {
      const startTime = performance.now();
      
      try {
        validateCsvContent(rawText, type === 'url' ? name : '');
      } catch (validationErr) {
        reject(validationErr);
        return;
      }

      Papa.parse(rawText, {
        header: true,
        skipEmptyLines: 'greedy',
        dynamicTyping: true,
        complete: (results) => {
          const endTime = performance.now();
          const parseTimeMs = Math.round(endTime - startTime);

          if (results.errors && results.errors.length > 0) {
            const fatalError = results.errors.find(
              (e) => e.type === 'Delimiter' || e.code === 'UndetectableDelimiter'
            );
            if (fatalError) {
              reject(new Error(`CSV parsing failed: ${fatalError.message}`));
              return;
            }
          }

          if (!results.data || results.data.length === 0) {
            reject(new Error('No data rows found in the CSV file.'));
            return;
          }

          const extractedCols = results.meta.fields || Object.keys(results.data[0] || {});
          if (extractedCols.length === 0) {
            reject(new Error('Could not identify valid headers in this CSV.'));
            return;
          }

          // Filter out null or undefined rows
          const cleanData = results.data.filter((row) =>
            Object.values(row).some((val) => val !== null && val !== undefined && val !== '')
          );

          // Calculate column types and stats
          const columnTypes = {};
          extractedCols.forEach((col) => {
            const sampleVals = cleanData
              .slice(0, 50)
              .map((r) => r[col])
              .filter((v) => v !== null && v !== undefined && v !== '');
            const isNumeric = sampleVals.length > 0 && sampleVals.every((v) => typeof v === 'number');
            columnTypes[col] = isNumeric ? 'number' : 'string';
          });

          const meta = {
            rowCount: cleanData.length,
            columnCount: extractedCols.length,
            fileSize: fileSize || new Blob([rawText]).size,
            parseTimeMs,
            extractedAt: new Date().toLocaleString(),
            columnTypes,
            delimiter: results.meta.delimiter,
          };

          setCsvData(cleanData);
          setColumns(extractedCols);
          setFileName(name);
          setSourceType(type);
          setMetadata(meta);
          setError(null);

          resolve({ data: cleanData, columns: extractedCols, metadata: meta, rawText, fileName: name });
        },
        error: (err) => {
          reject(new Error(`Failed to parse CSV: ${err.message}`));
        },
      });
    });
  }, [validateCsvContent]);

  // Load from local file
  const loadLocalFile = useCallback(async (file) => {
    setIsLoading(true);
    setError(null);
    try {
      if (!file.name.toLowerCase().endsWith('.csv') && file.type && !file.type.includes('csv') && !file.type.includes('text')) {
        throw new Error(`"${file.name}" is not a recognized CSV file format. Please upload a file with .csv extension.`);
      }

      const reader = new FileReader();
      return await new Promise((resolve, reject) => {
        reader.onload = async (e) => {
          try {
            const content = e.target.result;
            const res = await parseCsvText(content, file.name, 'local', file.size);
            resolve(res);
          } catch (err) {
            setError(err.message);
            reject(err);
          } finally {
            setIsLoading(false);
          }
        };
        reader.onerror = () => {
          const err = new Error('Failed to read the local file from disk.');
          setError(err.message);
          setIsLoading(false);
          reject(err);
        };
        reader.readAsText(file);
      });
    } catch (err) {
      setError(err.message);
      setIsLoading(false);
      throw err;
    }
  }, [parseCsvText]);

  // Load from Link / URL with redirects and validation
  const loadFromUrl = useCallback(async (url) => {
    setIsLoading(true);
    setError(null);
    try {
      let cleanUrl = url.trim();
      if (!cleanUrl.startsWith('http://') && !cleanUrl.startsWith('https://')) {
        throw new Error('Please enter a valid URL beginning with https:// or http://');
      }

      let response;
      let text;

      try {
        response = await fetch(cleanUrl, {
          method: 'GET',
          headers: {
            Accept: 'text/csv, text/plain, */*',
          },
        });
      } catch (fetchErr) {
        try {
          const proxyUrl = `https://corsproxy.io/?${encodeURIComponent(cleanUrl)}`;
          response = await fetch(proxyUrl);
        } catch (proxyErr) {
          throw new Error(
            `Unable to connect to the provided link (${cleanUrl}). The server might be unreachable or blocking access: ${fetchErr.message}`
          );
        }
      }

      if (!response.ok) {
        throw new Error(
          `Failed to fetch CSV: Server responded with status ${response.status} (${response.statusText}). Link does not redirect to an accessible CSV.`
        );
      }

      const contentType = response.headers.get('content-type') || '';
      if (
        contentType.includes('text/html') ||
        contentType.includes('application/xhtml+xml')
      ) {
        throw new Error(
          `Invalid CSV link: The URL returned "${contentType}". It points to a web page rather than raw CSV data.`
        );
      }

      text = await response.text();

      let inferredName = cleanUrl.split('/').pop().split('?')[0];
      if (!inferredName) {
        inferredName = 'remote-dataset.csv';
      } else if (!inferredName.toLowerCase().endsWith('.csv')) {
        inferredName = `${inferredName}.csv`;
      }

      const res = await parseCsvText(text, inferredName, 'url', new Blob([text]).size);
      return res;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [parseCsvText]);

  // Load Sample Data (from bundled sample-data.csv)
  const loadSampleData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch('/sample-data.csv');
      if (!response.ok) {
        throw new Error('Failed to load sample dataset from local server.');
      }
      const text = await response.text();
      const res = await parseCsvText(text, 'sample-data.csv', 'sample');
      return res;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [parseCsvText]);

  // Reset
  const clearData = useCallback(() => {
    setCsvData([]);
    setColumns([]);
    setFileName('');
    setSourceType(null);
    setMetadata(null);
    setError(null);
    try {
      sessionStorage.removeItem(CSV_STORAGE_KEY);
    } catch {}
  }, []);

  const value = useMemo(() => ({
    csvData,
    setCsvData,
    columns,
    setColumns,
    fileName,
    sourceType,
    metadata,
    isLoading,
    error,
    setError,
    warning,
    setWarning,
    parseCsvText,
    loadLocalFile,
    loadFromUrl,
    loadSampleData,
    clearData,
  }), [
    csvData,
    columns,
    fileName,
    sourceType,
    metadata,
    isLoading,
    error,
    warning,
    parseCsvText,
    loadLocalFile,
    loadFromUrl,
    loadSampleData,
    clearData,
  ]);

  return <CsvContext.Provider value={value}>{children}</CsvContext.Provider>;
};
