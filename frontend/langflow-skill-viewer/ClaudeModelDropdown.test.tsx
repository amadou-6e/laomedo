import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { DropdownOptionsList } from "@/components/core/dropdownComponent/components/DropdownOptionsList";
import { DropdownTrigger } from "@/components/core/dropdownComponent/components/DropdownTrigger";
import { useDropdownOptions } from "@/components/core/dropdownComponent/hooks/useDropdownOptions";

jest.mock("@/CustomNodes/GenericNode/components/NodeDialogComponent",()=>({__esModule:true,default:()=>null}));
jest.mock("@/components/common/genericIconComponent",()=>({__esModule:true,default:()=>null}));
jest.mock("@/components/common/loadingTextComponent",()=>({__esModule:true,default:()=>null}));
jest.mock("@/components/common/shadTooltipComponent",()=>({__esModule:true,default:({children}:any)=><>{children}</>}));
jest.mock("@/components/ui/command",()=>({
 CommandGroup:({children}:any)=><div>{children}</div>,CommandList:({children}:any)=><div>{children}</div>,
 CommandSeparator:()=>null,CommandItem:({children,onSelect,value,...props}:any)=><button {...props} onClick={()=>onSelect?.(value)}>{children}</button>,
}));
jest.mock("@/components/ui/button",()=>({Button:({children,...props}:any)=><button {...props}>{children}</button>}));
jest.mock("@/components/ui/popover",()=>({PopoverTrigger:({children}:any)=><>{children}</>}));
jest.mock("@/utils/utils",()=>({cn:(...items:any[])=>items.filter(x=>typeof x==='string').join(' ')}));
jest.mock("@/utils/stringManipulation",()=>({getStatusColor:()=>'',convertStringToHTML:(v:string)=>v}));
jest.mock("react-i18next",()=>({useTranslation:()=>({t:(key:string)=>key})}));

const metadata=[{id:'sonnet',laomedo_native_model:true,display_name:'Sonnet test',resolved_model:'claude-sonnet-test'}];

test('native model labels and IDs are separate; selection submits the original ID',()=>{
 const select=jest.fn();
 render(<DropdownOptionsList {...({filteredOptions:['sonnet'],filteredMetadata:metadata,firstWord:'Model',value:'sonnet',
  onSelect:select,setOpen:jest.fn(),setWaitingForResponse:jest.fn(),sourceOptions:{},
  handleSourceOptions:jest.fn(),handleRefreshButtonPress:jest.fn(),openDialog:false,setOpenDialog:jest.fn(),setPendingSelect:jest.fn()} as any)}/>);
 expect(screen.getByText('Sonnet test')).toBeVisible();expect(screen.getByText('claude-sonnet-test')).toBeVisible();
 expect(screen.queryByText(/display_name|resolved_model/)).toBeNull();
 fireEvent.click(screen.getByTestId('sonnet-0-option'));
 expect(select).toHaveBeenCalledWith('sonnet',undefined,undefined,metadata[0]);
});

test('selected native label is shown without changing ordinary dropdown text',()=>{
 const props:any={validOptions:['sonnet'],open:false,id:'model',value:'sonnet',options:['sonnet'],filteredOptions:['sonnet'],
 filteredMetadata:metadata,refButton:{current:null}};
 const {rerender}=render(<DropdownTrigger {...props}/>);
 expect(screen.getByRole('combobox')).toHaveTextContent('Sonnet test');
 rerender(<DropdownTrigger {...props} filteredMetadata={undefined}/>);
 expect(screen.getByRole('combobox')).toHaveTextContent('sonnet');
 rerender(<DropdownTrigger {...props} filteredMetadata={[{...metadata[0],laomedo_native_model:false}]}/>);
 expect(screen.getByRole('combobox')).toHaveTextContent('sonnet');
});

test('search finds the native display name and resolved model ID while retaining selection IDs',async()=>{
 const {result}=renderHook(()=>useDropdownOptions({value:'sonnet',options:['sonnet'],validOptions:['sonnet'],
 optionsMetaData:metadata,hasChildren:false,onSelect:jest.fn()}));
 await act(async()=>{await result.current.searchRoleByTerm({target:{value:'Sonnet test'}} as any)});
 expect(result.current.filteredOptions).toEqual(['sonnet']);
 await act(async()=>{await result.current.searchRoleByTerm({target:{value:'claude-sonnet-test'}} as any)});
 expect(result.current.filteredOptions).toEqual(['sonnet']);
});

test('metadata-only refresh updates a closed selector without changing option IDs',()=>{
 const {result,rerender}=renderHook(({items})=>useDropdownOptions({value:'sonnet',options:['sonnet'],validOptions:['sonnet'],
 optionsMetaData:items,hasChildren:false,onSelect:jest.fn()}),{initialProps:{items:metadata}});
 const updated=[{...metadata[0],display_name:'Sonnet newer'}];rerender({items:updated});
 expect(result.current.filteredMetadata).toEqual(updated);
});
