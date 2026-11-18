import { cn } from "@/lib/utils";

/** Cabecera común de cada módulo: título, descripción opcional y acciones a la derecha. */
export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0">
        <h1 className="page-title">{title}</h1>
        {description ? <p className="page-subtitle">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2 sm:justify-end">{actions}</div> : null}
    </header>
  );
}

/** Superficie de sección: un solo nivel de contenedor, sin tarjetas anidadas. */
export const SURFACE = "rounded-[0.9rem] border border-crema/[0.07] bg-crema/[0.025]";
