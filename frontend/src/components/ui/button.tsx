import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-[0.7rem] text-sm font-medium transition-[background-color,border-color,color,transform] duration-150 ease-out-strong active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-arcilla focus-visible:ring-offset-2 focus-visible:ring-offset-carbon disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default:     "bg-arcilla text-tinta hover:bg-arcilla/90",
        outline:     "border border-crema/15 bg-transparent text-crema hover:border-crema/25 hover:bg-crema/[0.05]",
        ghost:       "text-crema hover:bg-musgo/20",
        destructive: "bg-red-700/80 text-crema hover:bg-red-700",
        secondary:   "bg-musgo text-crema hover:bg-musgo/80",
      },
      size: {
        sm:   "h-8 px-3 text-xs",
        md:   "h-10 px-4",
        lg:   "h-11 px-6 text-base",
        icon: "h-10 w-10 p-0",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  }
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
);
Button.displayName = "Button";

export { Button, buttonVariants };
