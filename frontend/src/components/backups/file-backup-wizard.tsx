"use client";

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { useAgents, useAgentJob } from '@/hooks/useAgents';
import { useManagedAgentProfiles } from '@/hooks/useAgentProfilesAdmin';
import { agentProfilesService } from '@/services/agent-profiles.service';
import { fileBackupsService } from '@/services/file-backups.service';
import { FILE_BACKUP_KEYS } from '@/hooks/useFileBackups';
import { formatBytes } from '@/lib/utils';
import type { FileBackupStrategy, FileBackupTaskInput } from '@/types/file-backup';

const INPUT = 'mt-1 w-full rounded-lg border border-musgo/30 bg-surface px-3 py-2 text-sm text-crema';
const BUTTON = 'rounded-lg border border-musgo/30 px-4 py-2 text-sm text-crema disabled:opacity-40';
const DAYS = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'];

function message(error: unknown) {
  const response = (error as { response?: { data?: { message?: string; detail?: unknown } } }).response?.data;
  if (typeof response?.message === 'string') return response.message;
  if (typeof response?.detail === 'string') return response.detail;
  return 'No se pudo completar la operación. Revisa la conexión y los datos.';
}

export default function FileBackupWizard({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const agents = useAgents();
  const [step, setStep] = useState(0);
  const [agentId, setAgentId] = useState('');
  const profiles = useManagedAgentProfiles(agentId || null);
  const [name, setName] = useState('');
  const [paths, setPaths] = useState('');
  const [recursive, setRecursive] = useState(true);
  const [excludeTmp, setExcludeTmp] = useState(true);
  const [destinationId, setDestinationId] = useState('');
  const [localPath, setLocalPath] = useState('');
  const [strategy, setStrategy] = useState<FileBackupStrategy>('incremental');
  const [weekdays, setWeekdays] = useState([0,1,2,3,4]);
  const [time, setTime] = useState('02:00');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [simulationId, setSimulationId] = useState<string | null>(null);
  const [destinationJobId, setDestinationJobId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const destinationJob = useAgentJob(destinationJobId);
  const simulation = useQuery({
    queryKey: ['file-simulation', simulationId], enabled: Boolean(simulationId),
    queryFn: () => fileBackupsService.simulation(simulationId!),
    refetchInterval: query => ['completed','failed','cancelled'].includes(query.state.data?.status ?? '') ? false : 1500,
  });
  const destinations = profiles.data?.items.filter(p => p.profileType === 'destination' && p.isActive && ['local','smb','smb_direct'].includes(String(p.publicConfig.type))) ?? [];
  const selected = destinations.find(p => p.id === destinationId);
  const validSources = paths.split('\n').map(p => p.trim()).filter(Boolean);
  const valid = step === 0 ? Boolean(name.trim() && agentId && validSources.length) : step === 1 ? selected?.syncStatus === 'applied' : weekdays.length > 0 && /^\d{2}:\d{2}$/.test(time);
  const ready = simulation.data?.status === 'completed' && destinationJob.data?.status === 'completed';

  async function createDestination() {
    setBusy(true); setError('');
    try {
      const profile = await agentProfilesService.create(agentId, { profileType:'destination', label:name.trim() || 'Destino de archivos', publicConfig:{ type:'local', path:localPath.trim() } });
      setDestinationId(profile.id);
      await profiles.refetch();
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }

  async function verify() {
    setBusy(true); setError(''); setSimulationId(null); setDestinationJobId(null);
    try {
      let id = taskId;
      if (!id) {
        const input: FileBackupTaskInput = {
          name:name.trim(), agentId, destinationProfileId:destinationId,
          sources:validSources.map(path => ({path,includeSubfolders:recursive})),
          filters:excludeTmp ? [{kind:'exclude',operator:'extension',pattern:'.tmp',isEnabled:true}] : [],
          strategy, format:'direct', schedule:{weekdays,localTime:time},
          timezoneName:'America/Mexico_City', retentionFullChains:4, isActive:false,
        };
        const task = await fileBackupsService.create(input);
        id = task.id; setTaskId(id);
        void client.invalidateQueries({queryKey:FILE_BACKUP_KEYS.tasks});
      }
      const [test, scan] = await Promise.all([fileBackupsService.testDestination(id), fileBackupsService.simulate(id)]);
      setDestinationJobId(test.jobId); setSimulationId(scan.id);
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }

  async function activate() {
    if (!taskId || !ready) return;
    setBusy(true); setError('');
    try {
      await fileBackupsService.update(taskId, {isActive:true});
      await client.invalidateQueries({queryKey:FILE_BACKUP_KEYS.tasks});
      onClose();
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }

  return <div className="fixed inset-0 z-50 !m-0 flex justify-end bg-black/40">
    <section role="dialog" aria-modal="true" aria-labelledby="file-wizard-title" className="flex h-full w-full max-w-xl flex-col border-l border-musgo/25 bg-surface shadow-xl">
      <header className="flex items-center justify-between border-b border-musgo/25 p-5"><h2 id="file-wizard-title" className="text-xl font-semibold text-crema">Proteger carpetas</h2><button aria-label="Cerrar asistente" onClick={onClose}><X size={20}/></button></header>
      <p className="border-b border-musgo/20 px-5 py-3 text-sm text-muted">Paso {step+1} de 4 · {['Qué proteger','Dónde guardarlo','Cuándo y cómo','Revisar y activar'][step]}</p>
      <div className="flex-1 space-y-5 overflow-y-auto p-5">
        {step === 0 && <>
          <label className="block text-sm text-muted">Nombre de la tarea<input className={INPUT} value={name} onChange={e=>setName(e.target.value)} /></label>
          <label className="block text-sm text-muted">Servidor<select className={INPUT} value={agentId} onChange={e=>{setAgentId(e.target.value);setDestinationId('');}}><option value="">Selecciona un servidor</option>{agents.data?.items.filter(a=>a.online).map(a=><option key={a.id} value={a.id}>{a.hostname}</option>)}</select></label>
          <label className="block text-sm text-muted">Carpetas de origen<textarea className={`${INPUT} min-h-28`} value={paths} onChange={e=>setPaths(e.target.value)} placeholder={'C:\\Datos\\Documentos'} /><span className="mt-1 block text-xs">Una ruta absoluta por línea, en el servidor seleccionado.</span></label>
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={recursive} onChange={e=>setRecursive(e.target.checked)}/>Incluir subcarpetas</label>
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={excludeTmp} onChange={e=>setExcludeTmp(e.target.checked)}/>Excluir archivos temporales .tmp</label>
        </>}
        {step === 1 && <>
          <label className="block text-sm text-muted">Destino de la copia<select className={INPUT} value={destinationId} onChange={e=>setDestinationId(e.target.value)}><option value="">Selecciona un destino</option>{destinations.map(p=><option key={p.id} value={p.id}>{p.label} · {p.syncStatus === 'applied' ? 'Aplicado' : 'Aplicando…'}</option>)}</select></label>
          {selected && <p className="break-all text-sm text-muted">{String(selected.publicConfig.path)} · {selected.syncStatus === 'applied' ? 'Listo para comprobar' : selected.lastError || 'Esperando que el agente aplique el destino…'}</p>}
          <div className="space-y-3 rounded-lg border border-musgo/25 p-4"><h3 className="text-sm font-medium">Agregar carpeta de destino local</h3><label className="block text-sm text-muted">Ruta del destino<input className={INPUT} value={localPath} onChange={e=>setLocalPath(e.target.value)} placeholder={'C:\\Copias\\Archivos'}/></label><button className={BUTTON} disabled={busy || !localPath.trim()} onClick={createDestination}>{busy?'Guardando…':'Agregar destino'}</button><p className="text-xs text-muted">También puedes elegir un destino SMB aplicado desde la configuración del servidor.</p></div>
        </>}
        {step === 2 && <>
          <label className="block text-sm text-muted">Tipo de copia<select className={INPUT} value={strategy} onChange={e=>setStrategy(e.target.value as FileBackupStrategy)}><option value="full">Completa (Full)</option><option value="incremental">Incremental</option><option value="differential">Diferencial</option></select></label>
          <p className="text-sm text-muted">La primera copia siempre será completa. Las siguientes usarán el tipo elegido.</p>
          <fieldset><legend className="mb-2 text-sm">Días de copia</legend><div className="flex flex-wrap gap-2">{DAYS.map((day,index)=><button type="button" key={day} aria-pressed={weekdays.includes(index)} onClick={()=>setWeekdays(current=>current.includes(index)?current.filter(d=>d!==index):[...current,index].sort())} className={`${BUTTON} ${weekdays.includes(index)?'border-arcilla bg-arcilla/10 text-arcilla':''}`}>{day}</button>)}</div></fieldset>
          <label className="block text-sm text-muted">Hora de copia (Ciudad de México)<input type="time" className={INPUT} value={time} onChange={e=>setTime(e.target.value)} /></label>
          <p className="text-xs text-muted">Las copias se conservan en el destino. La limpieza automática todavía no está disponible.</p>
        </>}
        {step === 3 && <>
          <h3 className="font-semibold">{name}</h3><p className="whitespace-pre-line break-all text-sm text-muted">{paths}</p><p className="break-all text-sm text-muted">Destino: {String(selected?.publicConfig.path ?? '')}</p><p className="text-sm text-muted">{weekdays.map(d=>DAYS[d]).join(', ')} · {time} CDMX · {strategy}</p>
          <p className="text-sm text-muted">Se guardará pausada mientras comprobamos el destino y simulamos la copia sin respaldar archivos.</p>
          <button className={BUTTON} disabled={busy || Boolean(simulationId && simulation.data && !['completed','failed','cancelled'].includes(simulation.data.status))} onClick={verify}>{busy?'Preparando…':'Comprobar y simular'}</button>
          {destinationJobId && <p role="status" className="text-sm">Destino: {destinationJob.data?.status === 'completed'?'Escritura, lectura y verificación correctas':destinationJob.data?.status === 'failed'?'Falló la prueba del destino':'Comprobando…'}</p>}
          {simulationId && <p role="status" className="text-sm">Simulación: {simulation.data?.status === 'completed'?`${simulation.data.summary.summary?.filesTotal ?? 0} archivos · ${formatBytes(simulation.data.summary.summary?.bytesTotal ?? 0)}`:simulation.data?.status === 'failed'?'No fue posible simular. Revisa las rutas y permisos.':'Explorando…'}</p>}
          {taskId && <p className="text-xs text-muted">Si cierras, la tarea permanece pausada para revisarla después.</p>}
        </>}
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      </div>
      <footer className="flex items-center justify-between gap-3 border-t border-musgo/25 p-5"><button className={BUTTON} onClick={step>0&&!taskId?()=>setStep(step-1):onClose}>{step>0&&!taskId?'Anterior':'Cerrar'}</button>{step<3?<button className={BUTTON} disabled={!valid||busy} onClick={()=>setStep(step+1)}>Siguiente</button>:<button className={`${BUTTON} border-arcilla bg-arcilla/10 text-arcilla`} disabled={!ready||busy} onClick={activate}>Activar programación</button>}</footer>
    </section>
  </div>;
}
