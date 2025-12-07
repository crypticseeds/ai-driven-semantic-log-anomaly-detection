"use client";

import { useEffect, useState } from "react";

interface Cluster {
  cluster_id: number;
  cluster_size: number;
  centroid: number[];
  representative_logs: string[];
  created_at: string;
  updated_at: string;
}

interface ClusteringResult {
  status: string;
  n_clusters: number;
  n_outliers: number;
  total_logs: number;
  cluster_metadata: Record<number, Cluster>;
}

export default function ClusteringPage() {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clusteringResult, setClusteringResult] = useState<ClusteringResult | null>(null);
  const [selectedCluster, setSelectedCluster] = useState<number | null>(null);
  const [clusterDetails, setClusterDetails] = useState<any>(null);

  const apiBaseUrl =
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const fetchClusters = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(`${apiBaseUrl}/api/v1/logs/clustering/clusters?limit=100`);
      if (!response.ok) {
        throw new Error("Failed to fetch clusters");
      }
      const data = await response.json();
      setClusters(data.clusters || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch clusters");
    } finally {
      setLoading(false);
    }
  };

  const runClustering = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(`${apiBaseUrl}/api/v1/logs/clustering/run`, {
        method: "POST",
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to run clustering");
      }
      const data = await response.json();
      setClusteringResult(data);
      // Refresh clusters after clustering
      await fetchClusters();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run clustering");
    } finally {
      setLoading(false);
    }
  };

  const fetchClusterDetails = async (clusterId: number) => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(
        `${apiBaseUrl}/api/v1/logs/clustering/clusters/${clusterId}`
      );
      if (!response.ok) {
        throw new Error("Failed to fetch cluster details");
      }
      const data = await response.json();
      setClusterDetails(data);
      setSelectedCluster(clusterId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch cluster details");
    } finally {
      setLoading(false);
    }
  };

  const fetchOutliers = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(
        `${apiBaseUrl}/api/v1/logs/clustering/outliers?limit=50`
      );
      if (!response.ok) {
        throw new Error("Failed to fetch outliers");
      }
      const data = await response.json();
      setClusterDetails({ outliers: data.outliers, total: data.total });
      setSelectedCluster(-1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch outliers");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClusters();
  }, []);

  return (
    <div className="container mx-auto p-8">
      <h1 className="text-3xl font-bold mb-6">HDBSCAN Clustering Dashboard</h1>

      {error && (
        <div className="mb-4 p-4 bg-red-100 border border-red-400 rounded text-red-800">
          {error}
        </div>
      )}

      <div className="mb-6 space-y-4">
        <div className="p-4 border rounded">
          <h2 className="text-xl font-semibold mb-4">Clustering Actions</h2>
          <div className="space-x-2">
            <button
              onClick={runClustering}
              disabled={loading}
              className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-400"
            >
              {loading ? "Running..." : "Run Clustering"}
            </button>
            <button
              onClick={fetchClusters}
              disabled={loading}
              className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 disabled:bg-gray-400"
            >
              Refresh Clusters
            </button>
            <button
              onClick={fetchOutliers}
              disabled={loading}
              className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600 disabled:bg-gray-400"
            >
              View Outliers
            </button>
          </div>
        </div>

        {clusteringResult && (
          <div className="p-4 bg-green-50 border border-green-400 rounded">
            <h3 className="text-lg font-semibold mb-2">Last Clustering Result</h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-sm text-gray-600">Clusters Found</p>
                <p className="text-2xl font-bold">{clusteringResult.n_clusters}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">Outliers</p>
                <p className="text-2xl font-bold text-red-600">
                  {clusteringResult.n_outliers}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-600">Total Logs</p>
                <p className="text-2xl font-bold">{clusteringResult.total_logs}</p>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div>
          <h2 className="text-2xl font-semibold mb-4">
            Clusters ({clusters.length})
          </h2>
          {loading && clusters.length === 0 ? (
            <p className="text-gray-500">Loading clusters...</p>
          ) : clusters.length === 0 ? (
            <p className="text-gray-500">No clusters found. Run clustering first.</p>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {clusters.map((cluster) => (
                <div
                  key={cluster.cluster_id}
                  className={`p-4 border rounded cursor-pointer hover:bg-gray-50 ${
                    selectedCluster === cluster.cluster_id ? "bg-blue-50 border-blue-400" : ""
                  }`}
                  onClick={() => fetchClusterDetails(cluster.cluster_id)}
                >
                  <div className="flex justify-between items-center">
                    <div>
                      <h3 className="font-semibold">Cluster {cluster.cluster_id}</h3>
                      <p className="text-sm text-gray-600">
                        Size: {cluster.cluster_size} logs
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-gray-500">
                        Updated: {new Date(cluster.updated_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <h2 className="text-2xl font-semibold mb-4">
            {selectedCluster === -1
              ? "Outliers"
              : selectedCluster !== null
                ? `Cluster ${selectedCluster} Details`
                : "Cluster Details"}
          </h2>
          {loading && !clusterDetails ? (
            <p className="text-gray-500">Loading details...</p>
          ) : clusterDetails ? (
            <div className="p-4 border rounded">
              {selectedCluster === -1 ? (
                <div>
                  <p className="mb-4 text-gray-600">
                    Total outliers: {clusterDetails.total}
                  </p>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {clusterDetails.outliers?.map((outlier: any, idx: number) => (
                      <div key={idx} className="p-3 bg-red-50 border border-red-200 rounded">
                        <div className="flex justify-between items-start mb-2">
                          <div>
                            <p className="font-semibold text-sm">{outlier.service}</p>
                            <p className="text-xs text-gray-500">{outlier.level}</p>
                          </div>
                          <p className="text-xs text-gray-500">
                            {new Date(outlier.timestamp).toLocaleString()}
                          </p>
                        </div>
                        <p className="text-sm">{outlier.message}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div>
                  <div className="mb-4">
                    <p className="text-sm text-gray-600">Cluster Size</p>
                    <p className="text-2xl font-bold">{clusterDetails.cluster_size}</p>
                  </div>
                  <div className="mb-4">
                    <p className="text-sm text-gray-600 mb-2">Sample Logs</p>
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {clusterDetails.sample_logs?.map((log: any, idx: number) => (
                        <div key={idx} className="p-3 bg-gray-50 border rounded">
                          <div className="flex justify-between items-start mb-2">
                            <div>
                              <p className="font-semibold text-sm">{log.service}</p>
                              <p className="text-xs text-gray-500">{log.level}</p>
                            </div>
                            <p className="text-xs text-gray-500">
                              {new Date(log.timestamp).toLocaleString()}
                            </p>
                          </div>
                          <p className="text-sm">{log.message}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-gray-500">Select a cluster to view details</p>
          )}
        </div>
      </div>
    </div>
  );
}

