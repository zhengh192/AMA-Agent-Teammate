import { useEffect, useRef } from "react";

async function importPlotly() {
  return import("plotly.js-dist-min");
}

interface PlotlyFigureProps {
  figure: { data: unknown[]; layout: Record<string, unknown> };
}

export function PlotlyFigure({ figure }: PlotlyFigureProps) {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    let loaded: Awaited<ReturnType<typeof importPlotly>> | null = null;
    void (async () => {
      loaded = await importPlotly();
      const { default: Plotly } = loaded;
      if (active && root.current) {
        await Plotly.react(root.current, figure.data as Plotly.Data[], figure.layout, {
          displaylogo: false,
          responsive: true,
          scrollZoom: false,
        });
      }
    })();
    return () => {
      active = false;
      if (loaded && root.current) loaded.default.purge(root.current);
    };
  }, [figure]);

  return <div className="plotly-chart" ref={root} aria-label="Analysis chart" />;
}
