import React,{createContext,useContext,useEffect,useRef,useState} from 'react';
import type {State,Reader} from './contracts';
import {localRequest} from './localService';
import {Button,StateNotice} from './components';
type Snapshot={schema_version:1;state:State;revision:number;reader:Reader;simulation:boolean;result?:unknown};
type Store={state:State;reader:Reader;setReader:(reader:Reader)=>Promise<void>;simulation:boolean;revision:number;busy:boolean;command:<T=any>(name:string,payload?:Record<string,unknown>,message?:string)=>Promise<T|undefined>;reload:()=>Promise<void>;reset:()=>Promise<any>;notice:string;setNotice:(notice:string)=>void};
const Context=createContext<Store>(null!);
export function Repository({children}:{children:React.ReactNode}){
 const [snapshot,setSnapshot]=useState<Snapshot|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const current=useRef<Snapshot|null>(null),queue=useRef<Promise<unknown>>(Promise.resolve());
 function accept(value:Snapshot){if(value.schema_version!==1||!value.state||!Number.isInteger(value.revision))throw Error('Invalid application response');current.current=value;setSnapshot(value);}
 async function reload(reader?:Reader){setLoading(true);setError('');try{accept(await localRequest<Snapshot>('application/read',{reader:reader||current.current?.reader}));}catch(e){setError((e as Error).message);}finally{setLoading(false);}}
 useEffect(()=>{void reload();},[]);
 async function command<T=any>(name:string,payload:Record<string,unknown>={},message=''):Promise<T|undefined>{
  const work=async()=>{setBusy(true);try{const s=current.current;if(!s)throw Error('Load the local workspace first');const reply=await localRequest<Snapshot>('application/command',{name,payload,expected_revision:s.revision,reader:s.reader});accept(reply);if(message)setNotice(message);return reply.result as T;}catch(e){setNotice(`Error: ${(e as Error).message}`);return undefined;}finally{setBusy(false);}};
  const next=queue.current.then(work,work);queue.current=next;return next;
 }
 if(loading)return <main className="connected-main"><p role="status">Loading local ontology workspace…</p></main>;
 if(error||!snapshot)return <main className="connected-main"><StateNotice kind="error" title="Local workspace unavailable">{error||'No application state returned.'} No fictional fallback is used.</StateNotice><Button onClick={()=>void reload()}>Retry local connection</Button></main>;
 return <Context.Provider value={{state:snapshot.state,reader:snapshot.reader,simulation:snapshot.simulation,revision:snapshot.revision,busy,command,reload:()=>reload(),setReader:reader=>reload(reader),reset:()=>command('workspace.reset',{},'Fixture workspace reset.'),notice,setNotice}}>{children}{busy&&<div className="server-saving" role="status">Saving / resolving with local service…</div>}</Context.Provider>;
}
export const useRepo=()=>useContext(Context);
